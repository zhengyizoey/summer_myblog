# coding=utf-8
from sqlalchemy import create_engine, Column, String, Boolean, Float, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta

from transwrap.db import next_id
import time

engine = create_engine("mysql+pymysql://root:zhengyi@127.0.0.1:3306/awesome?charset=utf8", pool_recycle=3600)  # , echo=True ,,
Base = declarative_base()
Session = sessionmaker(bind=engine)
session = Session()


def as_dict(self):
    temp = [0]
    def trans(self):
        temp[0] += 1
        d = {}
        l = [attr for attr in dir(self) if not attr.startswith('_')\
             and not callable(getattr(self, attr)) and attr != 'metadata']
        for c in l:
            result = getattr(self, c)
            if temp[0] < 2 and isinstance(result, list) and len(result) > 0:
                d[c] = [trans(x) for x in result]
            elif temp[0] < 2 and isinstance(result.__class__, DeclarativeMeta):
                d[c] = trans(result)
            elif temp[0] >= 2 and isinstance(result.__class__, DeclarativeMeta) or isinstance(result, list):
                d[c] = None
            else:
                d[c] = result
        temp[0] -= 1
        return d
    return trans(self)
    # return {c.name: getattr(self, c.name) for c in self.__table__.columns} # 不能处理relations

Base.as_dict = as_dict

class User(Base):
    __tablename__ = 'users'
    id = Column(String(50), primary_key=True, default=next_id)
    email = Column(String(50), nullable=False)
    password = Column(String(50), nullable=False)
    admin = Column(Boolean)
    name = Column(String(50), nullable=False)
    image = Column(String(500))
    created_at = Column(Float, nullable=False, default=time.time)
    blogs = relationship('Blog', backref='userinfo', lazy='select')  # relationship保存两表关系，数据库中并不存在
    comments = relationship('Comment', backref='userinfo', lazy='select')  # 正向查询blogs,反向查询引用：backref=' '


class Blog(Base):
    __tablename__ = 'blogs'
    id = Column(String(50), primary_key=True, default=next_id) # , collation='utf8_bin'
    user = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)  # 默认为null
    category = Column(ForeignKey('categories.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(50), nullable=False)
    summary = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)
    comments =relationship('Comment', backref='bloginfo', lazy='select')


class Comment(Base):
    __tablename__ = 'comments'
    id = Column(String(50), primary_key=True, default=next_id)
    blog = Column(ForeignKey('blogs.id', ondelete='CASCADE'),  nullable=False)
    user = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(Float, default=time.time)


class Category(Base):
    __tablename__ = 'categories'
    id = Column(String(50), primary_key=True, default=next_id)
    name = Column(String(50))
    blogs = relationship('Blog', backref='cateinfo', lazy='select')


if __name__ == '__main__':
    '''
    1、将db中多有老表改名为oldusers
        alter table blogs rename oldblogs;
        alter table users rename oldusers;
        alter table comments rename oldcomments;
    2、通过sqlalchem创建新表：
       Base.metadata.create_all(engine)

    3、数据库，将老表数据复制到新表
        insert into users
        select id, email, password, admin,name,image,created_at
        from oldusers;

        insert into blogs
        select id,user_id,name,summary,content,created_at
        from oldblogs;

        insert into comments
        select id,blog_id,user_id,content,created_at from oldcomments;
    4、修改编码问题
        4.1
        alter table blogs character set utf8; # 没用，表改了，字段还是Latin
        set character_set_client = utf8;
        set character_set_server = utf8;
        set character_set_connection = utf8;
        set character_set_database = utf8;
        set character_set_results = utf8;
        set collation_connection = utf8_general_ci;
        set collation_database = utf8_general_ci;
        set collation_server = utf8_general_ci;
        4.2
        删除表，重新创建，并将create_engine:charset=utf8 _没用，老表的utf8复制不过来
        show create table blogs;
        model里每一列指定：String(30, collation=utf8)指定行有用，表的默认还是latin1
        show full columns from blogs;
        4.3 我要打人了。。。
        数据库检查，几个默认都是utf8，突然想到。。database，改为utf8 OK
    5、增加category分类，创建表，blog.category null
        插入category元素，为所有blog.category赋值，然后改not null



    '''

    #Base.metadata.create_all(engine)
    # blog = session.query(Blog).first()
    # print dir(blog)
    # print blog.cate.id


    # 增加一条category
    # c = Category(name='Python web')
    # session.add(c)
    # session.commit()
    # alter table blogs  add category varchar(50);
    # alter table blogs add foreign key(category) references  categories(id) on delete cascade;
    # 将所有分类改为
    # c = session.query(Category).first()
    # session.query(Blog).update({Blog.category: c.id})
    # session.commit()
    # # 修改字段not null，还要把原来的类型也写上。。。
    # # alter table blogs modify category varchar(50) NOT NULL;
    '''
    query.one() id 多/没有 报错 query.one_or_none() 返回一个或者none
    query.first() 返回一个 或者 none

    '''
    # 因为blogs 将create_at 改为created_at太慢了，只好全部删表，重新来
    # def test():
    #     c=session.query(Category).filter(Category.id=='001492903953085457cde531eb24cd1813c78695a41dcfe000').first()
    #     print as_dict(c)
    #
    # test()
    server_cat_id = '001493378924079fd75d9d8fa7b4fd5ad497b10fcff9576000'
    cat = session.query(Category).filter(Category.id == '001492903953085457cde531eb24cd1813c78695a41dcfe000').first()



    print as_dict(cat)
    print cat.as_dict()
    import json
    print json.dumps(cat.as_dict())

