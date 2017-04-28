# coding=utf-8
import logging, json, functools
from transwrap.web import ctx

def api(func):
    @functools.wraps(func)
    def _wraper(*args, **kwargs):
        try:
            r = json.dumps(func(*args, **kwargs))
        except APIError, e:
            r = json.dumps(dict(error=e.error, data=e.data, message=e.message))
        # except TypeError:
        #     func_result = func(*args, **kwargs)
        #     if isinstance(func_result, list):
        #         r = json.dumps([object_.as_dict() for object_ in func_result])
        #     r = json.dumps(func_result.as_dict())
        except Exception, e:
            logging.exception(e)
            r = json.dumps(dict(error='internalerror', data=e.__class__.__name__, message=e.message))
        ctx.response.conten_type = 'application/json'
        return r
    return _wraper


class APIError(StandardError):
    def __init__(self, error, data='', message=''):
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message


# 输入不合法 error field of input form
class APIValueError(APIError):
    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)

# 资源未找到
class APIRresourNotFound(APIError):
    def __init__(self, field, message=''):
        super(APIRresourNotFound, self).__init__('value:notfound', field, message)

# 权限异常
class APIPermissionError(APIError):
    def __init__(self, message=''):
        super(APIPermissionError, self).__init__('permission:forbidden', 'permission', message)
