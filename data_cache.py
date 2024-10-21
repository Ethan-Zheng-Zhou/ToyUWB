'''
    data_cache.py : 用来构建一个全局的数据队列 data_queue变量，单设备使用只需队列来存储
'''
from queue import Queue

### define a global queue
global data_queue
data_queue = Queue()