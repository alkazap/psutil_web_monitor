import asyncio
import json
import logging
import os
import threading
import time

import psutil
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/', IndexHandler),
            (r'/sysinfo', SysInfoSocketHandler)
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), 'templates'),
            static_path=os.path.join(os.path.dirname(__file__), 'static')
        )
        tornado.web.Application.__init__(self, handlers, **settings)
        self.sys_info_socket_list = set()

    def get_sys_info(self):
        sys_info = {cpu_num: {'procs': {}, 'cpu_percent': 0, 'memory_percent': 0}
                    for cpu_num in range(psutil.cpu_count())}
        for proc in psutil.process_iter(attrs=['cmdline', 'cpu_num', 'memory_percent']):
            proc_name = ''
            # Only get info of python processes
            if len(proc.info['cmdline']) > 1 and 'python' in proc.info['cmdline'][0]:
                cmdline = ' '.join(proc.info['cmdline'])
                if 'multiprocessing' in cmdline:
                    if 'semaphore_tracker' in cmdline:
                        proc_name = 'mp_tracker'
                    else:
                        proc_name = 'mproc'
                elif '.py' in proc.info['cmdline'][1]:
                    proc_name = proc.info['cmdline'][1].split('.')[0]
            if len(proc_name) > 0:
                proc_info = proc.as_dict(
                    attrs=['pid', 'cpu_percent', 'memory_percent', 'num_threads'])
                proc_info['name'] = proc_name
                # if len(proc_info['cpu_affinity']) == psutil.cpu_count():
                #    proc_info['cpu_affinity'] = "all"
                #import datetime
                #proc_info['create_time'] = datetime.datetime.fromtimestamp(proc_info['create_time']).strftime("%Y-%m-%d %H:%M:%S")
                proc_info['memory_percent'] = "%.1f" % proc_info['memory_percent']
                proc_num = len(sys_info[proc.info['cpu_num']]['procs'])
                sys_info[proc.info['cpu_num']]['procs'][proc_num] = proc_info
            sys_info[proc.info['cpu_num']]['memory_percent'] += proc.info['memory_percent']
        cpu_percent = psutil.cpu_percent(percpu=True)
        for cpu_num in range(psutil.cpu_count()):
            sys_info[cpu_num]['cpu_percent'] = cpu_percent[cpu_num]
            sys_info[cpu_num]['memory_percent'] = "%.1f" % sys_info[cpu_num]['memory_percent']
        return sys_info

    def send_sys_info_update(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        while True:
            if len(self.sys_info_socket_list) > 0:
                sys_info = self.get_sys_info()
                for ws in self.sys_info_socket_list:
                    ws.write_message(json.dumps(sys_info))
            time.sleep(1)


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.render('index.html')


class SysInfoSocketHandler(tornado.websocket.WebSocketHandler):
    def initialize(self):
        self.log = logging.getLogger(self.__class__.__name__)
        self.ip = None

    def open(self):
        self.ip = self.request.remote_ip
        self.log.info("A new sys info listener WebSocket(%s) is opened" %
                      (self.ip))
        self.application.sys_info_socket_list.add(self)

    def on_close(self):
        self.log.info("The sys info listener WebSocket(%s) is closed" %
                      (self.ip))
        self.application.sys_info_socket_list.discard(self)


def main():
    # Parse global options from the command line
    from tornado.options import define, options
    define('port', default=20005, type=int, help='Port to listen on')
    tornado.options.parse_command_line()

    # Initialize web application
    app = Application()
 
    # Start an HTTP server for this app
    app.listen(options.port)

    # Send sys info updates
    threading.Thread(target=app.send_sys_info_update, args=(),
                     name='SysInfoUpdate', daemon=True).start()

    try:
        # I/O event loop for non-blocking sockets
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        pass
    finally:
        tornado.ioloop.IOLoop.current().stop()
        # tornado.ioloop.IOLoop.current().close()



if __name__ == '__main__':
    main()
