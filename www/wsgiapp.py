# coding=utf-8
import logging; logging.basicConfig(level=logging.INFO)
import os, time, datetime
import markdown2

from transwrap import db
from transwrap.web import WSGIApplication, Jinja2TemplateEngine, ctx

from config import configs

from urls import f2time

def tomarkdown(text):
    return markdown2.markdown(text)

def touser(user):
    return ctx.request.user

db.create_engine(**configs.db)
wsgi = WSGIApplication(os.path.dirname(os.path.abspath(__file__)))  # document_root
template_engine = Jinja2TemplateEngine(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
template_engine.add_filter('totime', f2time)
template_engine.add_filter('touser', touser)
template_engine.add_filter('tomarkdown', tomarkdown)
wsgi.template_engine = template_engine
print wsgi.template_engine._env

import urls
wsgi.add_interceptor(urls.identify_user)
wsgi.add_module(urls)

if __name__ == '__main__':
    wsgi.run(9000)
else:
    application = wsgi.get_wsgi_application()


