# coding=utf-8
import db
import time
import logging

_triggers = frozenset(['pre_insert', 'pre_update', 'pre_delete'])



# 类->表：生成创建表的sql:'create table User `username` (每个列名拼接进来ddl not null,..);'
def _gen_sql(table_name, mappings):
    pk = None
    sql = ['--generating SQL for %s:' % table_name, 'create table `%s`(' % table_name]
    for f in sorted(mappings.values(), lambda x, y: cmp(x.__order, y.__order)):
        if not hasattr(f, 'ddl'):
            raise StandardError('no ddl in field "%s".' % f)
        ddl = f.ddl
        nullable = f.nullable
        if f.primary_key:
            pk = f.name
        sql.append('`%s` %s,' % (f.name, ddl) if nullable else '`%s` %s not null,' % (f.name, ddl))
    sql.append('primary key (`%s`)' % pk)
    sql.append(');')
    return '\n'.join(sql)


# TODO ddl,nullable,_default=time.time()或‘’
# 1、self.name,self.primary_key=kw.get('name');2、0rder按照次序；3、设置default
class Field(object):
    _count = 0

    def __init__(self, **kwargs):
        self.name = kwargs.get('name', None)
        self._default = kwargs.get('default', None)
        self.primary_key = kwargs.get('primary_key', False)
        self.nullable = kwargs.get('nullable', False)
        self.updatable = kwargs.get('updatable', True)
        self.insertable = kwargs.get('insertable', True)
        self.ddl = kwargs.get('ddl', '')
        self._order = Field._count  # 用于记录这个实例是第几个被实例化的,创建表sql是按次序
        Field._count += 1           # 类的count,这个类目前实例了几个实例。。。，+1

    @property
    def default(self):
        d = self._default
        return d() if callable(d) else d

    # <IntegerFielf:id,bigint,default(0),UI> => 类：实例：实例dll属性；实例default信息，3个标志位：N U I
    def __str__(self):
        s = ['<%s:%s,%s,default(%s),' % (self.__class__.__name__, self.name, self.ddl, self._default)]
        self.nullable and s.append('N')
        self.updatable and s.append('U')
        self.insertable and s.append('I')
        s.append('>')
        return ''.join(s)


# 这种字段的default处理
class StringField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = ''
        if 'ddl' not in kwargs:
            kwargs['ddl'] = 'varchar(255)'
        super(StringField, self).__init__(**kwargs)


class IntegerField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = 0
        if 'ddl' not in kwargs:
            kwargs['ddl'] = 'bigint'
        super(IntegerField, self).__init__(**kwargs)


class FloatField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = 0.0
        if 'ddl' not in kwargs:
            kwargs['ddl'] = 'real'
        super(FloatField, self).__init__(**kwargs)


class BooleanField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = False
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'bool'
        super(BooleanField, self).__init__(**kwargs)


class TextField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = ''
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'text'
        super(TextField, self).__init__(**kwargs)


class BlobField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = ''
        if not 'ddl' in kwargs:
            kwargs['ddl'] = 'blob'
        super(BlobField, self).__init__(**kwargs)


class VersionField(Field):
    def __init__(self, name=None):
        super(VersionField, self).__init__(name=name, default=0, ddl='bigint')


# Model类直接创建，User类处理attrs
# User类：1、将attrs里的Field处理后剔除进mappings； 2、__sql__ = _gen_sql() 创建表的sql,还未执行。。。
class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        if not hasattr(cls, 'subclasses'):
            cls.subclasses = {}
        if not name in cls.subclasses:
            cls.subclasses[name] = name
        else:
            logging.warning('redefine class:%s'%name)
        mappings = dict()
        primary_key = None
        for k, v in attrs.iteritems():   # 处理attrs:如果是Field的实例，再处理下，放入mappings字典
            if isinstance(v, Field):
                if not v.name:           # k,v => username=StringField(primary_key=True，name='username');列名
                    v.name = k
                logging.info('[mapping] found mapping:%s => %s' % (k, v))
                if v.primary_key:
                    if primary_key:
                        raise TypeError('Cannot define more than 1 primary key in class:%s' % name)
                    if v.updatable:
                        logging.warning('note:change primary key to non_updatable')
                        v.updatable = False
                    if v.nullable:
                        logging.warning('note:change primary key to non_nullable')
                        v.nullable = False
                    primary_key = v
                mappings[k] = v
        if not primary_key:
            raise TypeError('primary key not defined in class:%s'%name)
        for k in mappings.iterkeys(): # 先从attrs里找出Field的相关放入Mappings，然后从attrs里剔除这些（重复）
            attrs.pop(k)
        if not '__table__' in attrs:
            attrs['__table__'] = name.lower() # 如果没有表名，就取类名
        attrs['__mappings__'] = mappings
        attrs['__primary_key__'] = primary_key
        attrs['__sql__'] = lambda self: _gen_sql(attrs['__table__'], mappings)
        for trigger in _triggers:
            if not trigger in attrs:
                attrs[trigger] = None
        return type.__new__(cls, name, bases, attrs)


# 子类的映射关系，通过metaclass扫描进attrs，访问
class Model(dict):

    __metaclass__ =  ModelMetaclass

    def __init__(self, **kwargs):
        super(Model, self).__init__(**kwargs)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError('"Dict" object has no attribute %s '% item)

    def __setattr__(self, key, value):
        self[key] = value

    @classmethod
    def find_first(cls, where, *args):
        d = db.select_one('select * from %s %s'%(cls.__table__, where), *args)
        return cls(**d) if d else None


    @classmethod
    def get(cls, pk):
        # cls.__primary_key__.name    StringField.name
        d = db.select_one('select * from %s where %s=?'%(cls.__table__, cls.__primary_key__.name), pk)
        return cls(**d) if d else None

    @classmethod
    def find_all(cls, *args):
        L = db.select('select * from `%s`' % cls.__table__)
        return [cls(**d) for d in L]

    @classmethod
    def find_by(cls, where, *args):
        L = db.select('select * from `%s` %s' % (cls.__table__, where), *args)
        return [cls(**d) for d in L]

    @classmethod
    def count_all(cls):
        return db.select('select count(`%s`) from `%s`' % (cls.__primary_key__.name, cls.__table__))

    @classmethod
    def count_by(cls, where, *args):
        return db.select_int('select count(`%s`) from `%s` %s' % (cls.__primary_key__.name, cls.__table__, where),
                             *args)

    # 如果该行(实例）字段有updatable属性，该字段可以被更新
    def update(self):
        self.pre_update and self.pre_update()
        L = []
        args = []
        for k, v in self.__mappings__.iteritems():
            if v.updatable:
                if hasattr(self, k):
                    arg = getattr(self, k)
                else:
                    arg = v.default
                    setattr(self, k, arg)
                L.append('`%s`=?'% k)
                args.append(arg)
        pk = self.__primary_key__.name
        args.append(getattr(self, pk))
        db.update('update `%s` set %s where %s=?'% (self.__table__, ','.join(L), pk), *args)
        return self

    # 删除这一行：sql:delete from 'user' where 'id'=%s,args:(10190,)
    def delete(self):
        self.pre_delete and self.pre_delete()
        pk = self.__primary_key__.name
        args = (getattr(self, pk),)
        db.update('delete from `%s` where `%s` = ?'%(self.__table__, pk), *args)
        return self

    def insert(self):
        self.pre_insert and self.pre_insert()
        params = {}
        for k, v in self.__mappings__.iteritems():
            if v.insertable:
                if not hasattr(self, k):
                    setattr(self, k, v.default)
                params[v.name] = getattr(self, k)
        db.insert('%s' % self.__table__, **params)
        return self

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    db.create_engine('root', 'zhengyi', 'test')
    db.update('drop table if exists user')
    db.update('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
    import doctest
    doctest.testmod()









