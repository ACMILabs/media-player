import sys


def status_client():
    """
    Mock out the prometheus status_client for tests.
    """
    return 0

MODULE = type(sys)('status_client')
MODULE.status_client = status_client
sys.modules['status_client'] = MODULE
