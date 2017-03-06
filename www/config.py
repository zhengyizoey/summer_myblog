# coding=utf-8
import config_default
from transwrap.db import Dict
configs = config_default.configs


def merge(default, override):
    dict_ = {}
    for k, v in default.iteritems():
        if k in override:
            if isinstance(v, dict):
                dict_[k] = merge(v, override[k])
            else:
                dict_[k] = override[k]
        else:
            dict_[k] = v
    return dict_


def to_Dict(configs):
    D = Dict()
    for k, v in configs.iteritems():
        D[k] = to_Dict(v) if isinstance(v, dict) else v
    return D

try:
    import config_override
    configs = merge(configs, config_override.configs)
except ImportError:
    pass

configs = to_Dict(configs)
