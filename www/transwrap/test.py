# coding=utf-8
import time
import uuid
import functools
import threading
import logging

engine = None


# 生成唯一的一个id：当前时间+随机数
def next_id(t=None):
    if t is None:
        t = time.time()
    return '%015d%s000'%(int(t*1000), uuid.uuid4().hex)


# 剖析sql执行时间
def _profiling(start, sql=''):
    t = time.time() - start
    if t>0.1:
        logging.warning('[profiling] [db] %s:%s'%(t, sql))
    else:
        logging.info('[profiling] [db] %s:%s'%(t, sql))


# 保存create_engine创建的conn engine = _Engine(lambda :mysql.connector.connect(**params))
class _Engine(object):
    def __init__(self, connect):
        self._connect = connect
    def connect(self):
        return self._connect


# 根据engine(conn),提供cursor，rollback,close操作
class _LasyConnection(object):
    def __init__(self):
        self.connection = None

    def cursor(self):
        if self.connection is None:
            _connection = engine.connect()
            logging.info('[connection][open]connection <%s>...' % hex(id(_connection)))
            self.connection = _connection
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def cleanup(self):
        if self.connection:
            _connection = self.connection
            self.connection = None
            logging.info('[connection][close]connection<%s>...' % hex(id(connection)))
            _connection.close()


# 引用lasy,init:self.connection = _LasyConnection()
class _DbCtx(threading.local):
    def __init__(self):
        self.connection = None
        self.transaction = 0

    def is_init(self):
        return self.connection is not None

    def init(self):
        logging.info('open a lazy connection')
        self.connection = _LasyConnection()
        self.transaction = 0

    def cleanup(self):
        self.connection.cleanup()
        self.connection = None

    def cursor(self):
        return self.connection.cursor()

_db_ctx = _DbCtx()


# 连接的自动获取和释放，enter,exit实现对象的with方法
class _ConnectionCtx(object):
    def __enter__(self):
        global _db_ctx
        self.should_cleanup = False
        if not _db_ctx.is_init():
            _db_ctx.init()                # self.connection = _Lasyconnection()
            self.should_cleanup = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _db_ctx
        if self.should_cleanup:
            _db_ctx.cleanup()            # _Lasyconnection().cleanup()


class _TransactionCtx(object):
    def __enter__(self):
        global _db_ctx
        self.should_close_conn = False
        if not _db_ctx.is_init():
            _db_ctx.init()
            self.should_close_conn = True
        _db_ctx.transactions += 1
        logging.info('began transaction...'if _db_ctx.transactions == 1 else 'join current trasaction...')
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        global _db_ctx
        _db_ctx.transactions -= 1
        try:
            if _db_ctx.transactions == 0:
                if exc_type is None:
                    self.commit()
                else:
                    self.rollback()
        finally:
            if self.should_close_conn:
                _db_ctx.cleanup()
    def commit(self):
        global _db_ctx
        logging.info('commit transactions')
        try:
            _db_ctx.connection.commit()
            logging.info('commit ok')
        except:
            logging.warning('commit failed,try rollback...')
            _db_ctx.connection.rollback()
            logging.warning('rollback ok')
            raise
    def rollback(self):
        global _db_ctx
        logging.warning('rollback transaction...')
        _db_ctx.connection.rollback()
        logging.info('rollback ok')


# engine = _Engine(lambda :mysql.connector.connect(**params))
def create_engine(user, password, database, host='127.0.0.1', port=3306, **kwargs):
    import mysql.connector
    global engine
    if engine is not None:
        raise DBError('Enging is already initialized.')
    params = dict(user=user, password=password, database=database, host=host, port=port)
    defaults = dict(use_unicode=True, charset='utf8', collation='utf8_general_ci', autocommit=False)
    for k, v in defaults.iteritems():
        params[k] = kwargs.pop(k, v)
    params.update(kwargs)
    params ['buffered'] = True
    engine = _Engine(lambda : mysql.connector.connect(**params))
    print hex(id(engine))


def connection():
    return _ConnectionCtx()


# with _ConnectionCtx():....
def with_connection(func):
    @functools.wraps(func)
    def _wraper(*args, **kwargs):
        with _ConnectionCtx():
            return func(*args, **kwargs)
    return _wraper


def transaction():
    return _TransactionCtx()


def with_transaction(func):
    def _wraper(*args, **kwargs):
        start = time.time()
        with _TransactionCtx():
            func(*args, **kwargs)
        _profiling(start)
    return _wraper


# cursor = _db_ctx.connection.cursor().cursor.excute(sql, **kw)
@with_connection
def _select(sql, first, *args):  # first:表示要求查询结果第一条
    global _db_ctx
    cursor = None
    sql = sql.replace('?', '%s')
    logging.info('SQL:%s,args:%s'%(sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        if cursor.description:       # mysql.connector:cursor对象里如果有查询结果，返回结果集
            names = [x[0] for x in cursor.description]
        if first:
            values = cursor.fetchone()
            if not values:
                return None
            return Dict(names, values)
        return [Dict(names, x) for x in cursor.fetchall()]
    finally:
        if cursor:
            cursor.close()


def select_one(sql, *args):
    return _select(sql, first=True, *args)


def select_int(sql, *args):
    d = _select(sql, first=True, *args)
    if len(d) != 1:
        raise MultiColumnsError('Expect only one column')
    return d.values()[0]


def select(sql, *args):
    return _select(sql, first=False, *args)


@with_connection
def _update(sql, *args):
    global _db_ctx
    cursor = None
    sql = sql.replace('?', '%s')
    logging.info('sql:%s,args:%s'%(sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        r = cursor.rowcount
        if _db_ctx.transactions == 0:     # no transactions environment
            logging.info('auto commit')
            _db_ctx.connection.commit()
        return r
    finally:
        if cursor:
            cursor.close()


def update(sql, *args):
    return _update(sql, *args)


# TODO
def insert(table, **kwargs):
    cols, args = zip(*kwargs.iteritems())
    #sql = 'insert into %s (%s) values (%s)'%(table, ','.join([col for col in cols], ','.join(['?' for i in range(len(cols))])))
    sql = 'insert into `%s` (%s) values (%s)' % (table, ','.join(['`%s`' % col for col in cols]), ','.join(['?' for i in range(len(cols))]))
    return _update(sql, *args)


class Dict(dict):  # 定制： dict.key = value
    def __init__(self, names=(), values=(), **kwargs):
        super(Dict, self).__init__(**kwargs)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(r'Dict object has no attribute %s'%item)

    def __setattr__(self, key, value):
        self[key] = value


class DBError(Exception):pass


class MultiColumnsError(DBError):pass

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    create_engine(user='root', password='zhengyi', database='test', host='192.168.10.128')
    # update('drop table if exists user')
    # update('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
    import doctest
    doctest.testmod()
    print type(engine)
    print dir(engine)
    print engine.connect()
    print type(engine.connect())
    conn = engine.connect()
    print dir(conn)


    #
    # update('drop table if exists user')
    # update('create table user (id int primary key,name text, email text, password text)')