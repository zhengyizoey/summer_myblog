# coding=utf-8
import time
from transwrap.db import next_id
from transwrap.orm import Model, StringField, BooleanField, FloatField, TextField


class User(Model):
    __table__ = 'users'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    email = StringField(updatable=False, ddl='varchar(50)')
    password = StringField(ddl='varchar(5)')
    admin = BooleanField()
    name = StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(500)')
    created_at = FloatField(updatable=False, default=time.time)


class Blog(Model):
    __table__ = 'blogs'
    id = StringField(primary_key=True, default=next_id, ddl='varchar(5)')
    user_id = StringField(updatable=False, ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    name = StringField(ddl='varchar(50)')
    summary = StringField(ddl='varchar(200)')
    content = TextField()
    created_at = FloatField(updatable=False, default=time.time)

class Comment(Model):
    __table__ = 'comments'
    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    blog_id = StringField(updatable=False, ddl='varchar(50)')
    user_id = StringField(updatable=False, ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    content = TextField()
    created_at = FloatField(updatable=False, default=time.time)

if __name__ == '__main__':
    from transwrap.db import create_engine, select_one, select
    create_engine('root', 'zhengyi', 'awesome')
    import hashlib
    useradmin = User(name = 'zhengyiadmin',
                     email='hkj@qq.com',
                     password=hashlib.md5('zhengyiadmin').hexdigest(),
                     admin=True)
    useradmin.insert()

    # 1、修改数据库不完整关系；
    '''
    1、删除comments里blog_id指向为空的comments：
        delete  from comments where comments.blog_id not in
        (select id from blogs);
    2、删除comments里user_id指向为空的：
        delete from comments where comments.user_id not in
        (select id from users);
        delete from oldcomments where oldcomments.user_id not in
        (select id from oldusers);
    3、删除blogs里user_id指向为空的：
        delete from oldblogs where oldblogs.user_id not in
        (select id from oldusers);

    '''