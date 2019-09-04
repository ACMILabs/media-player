import sys


def status_client():
    return 0

module = type(sys)('status_client')
module.status_client = status_client
sys.modules['status_client'] = module
