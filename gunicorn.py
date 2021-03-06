import pickle
import tracemalloc

from google.cloud import pubsub, storage

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torchvision.models as models
from main import app

MODEL_PATH = './model.tsh'

class VGG_HASHNET(nn.Module):
    def __init__(self, pretrained=False):
        tracemalloc.start()
        super(VGG_HASHNET, self).__init__()
        self.object_extractor = models.vgg16(pretrained=True)
        self.object_extractor.classifier = nn.Sequential(*list(self.object_extractor.classifier.children())[:-2])
        self.object_extractor.eval()

        app.logger.warning(tracemalloc.take_snapshot())

        self.background_extractor = models.__dict__['alexnet'](num_classes=365)
        self.background_extractor.classifier = nn.Sequential(*list(self.background_extractor.classifier.children())[:-1])
        self.background_extractor.eval()

        self.fc1 = nn.Linear(4096 * 2, 4096)
#         self.fc1 = nn.DataParallel(self.fc1)
        self.fc2 = nn.Linear(4096,4096)
#         self.fc2 = nn.DataParallel(self.fc2)

        self.output = nn.Linear(4096,997)
        if pretrained:
            loaded = torch.load(MODEL_PATH, map_location='cpu')
            self.load_state_dict({ str.replace(k,'module.', ''): v for k,v in loaded.items() })
        else:
            checkpoint = torch.load('./alexnet_places365.pth.tar', map_location=lambda storage, loc: storage)
            state_dict = {str.replace(k,'module.',''): v for k,v in checkpoint['state_dict'].items()}
            self.background_extractor.load_state_dict(state_dict)

#         print(self.object_extractor)
#         print("============================")
#         print(self.background_extractor)
    def forward(self, x):
        obj_feat = self.object_extractor(x)
#         print(obj_feat.size())
        scene_feat = self.background_extractor(x)
#         print(scene_feat.size())
        feats = torch.cat((obj_feat, scene_feat), dim=1)
#         print(feats.size())
        output = self.fc1(feats)
        output = self.fc2(output)
        output = self.output(output)
#         print('Layer:', output)
        return torch.sigmoid(output)


# initializes model by loading into memory from trained model
def load_model():
    app.logger.info("loading")
    client = storage.Client()
    bucket = client.get_bucket("models_cta003")
    blob = bucket.get_blob("vgg_hashnet_r3_v7.pth")
    blob.download_to_filename("model.tsh")
    blob = bucket.get_blob("alexnet_places365.pth.tar")
    blob.download_to_filename("alexnet_places365.pth.tar")

    blob = bucket.get_blob("tag_map.pickle")
    blob.download_to_filename("tag_map.pickle")
    
    model = VGG_HASHNET(pretrained=True)
    tag_map = None
    with open("tag_map.pickle", "rb") as f:
        tag_map = pickle.load(f)

    app.logger.info("finished initial loading")
    app.config['MODEL'] = model
    app.config['TAG_MAP'] = tag_map

# Sample Gunicorn configuration file.

#
# Server socket
#
#   bind - The socket to bind.
#
#       A string of the form: 'HOST', 'HOST:PORT', 'unix:PATH'.
#       An IP is a valid HOST.
#
#   backlog - The number of pending connections. This refers
#       to the number of clients that can be waiting to be
#       served. Exceeding this number results in the client
#       getting an error when attempting to connect. It should
#       only affect servers under significant load.
#
#       Must be a positive integer. Generally set in the 64-2048
#       range.
#

bind = '127.0.0.1:8000'
backlog = 2048

#
# Worker processes
#
#   workers - The number of worker processes that this server
#       should keep alive for handling requests.
#
#       A positive integer generally in the 2-4 x $(NUM_CORES)
#       range. You'll want to vary this a bit to find the best
#       for your particular application's work load.
#
#   worker_class - The type of workers to use. The default
#       sync class should handle most 'normal' types of work
#       loads. You'll want to read
#       http://docs.gunicorn.org/en/latest/design.html#choosing-a-worker-type
#       for information on when you might want to choose one
#       of the other worker classes.
#
#       A string referring to a Python path to a subclass of
#       gunicorn.workers.base.Worker. The default provided values
#       can be seen at
#       http://docs.gunicorn.org/en/latest/settings.html#worker-class
#
#   worker_connections - For the eventlet and gevent worker classes
#       this limits the maximum number of simultaneous clients that
#       a single process can handle.
#
#       A positive integer generally set to around 1000.
#
#   timeout - If a worker does not notify the master process in this
#       number of seconds it is killed and a new worker is spawned
#       to replace it.
#
#       Generally set to thirty seconds. Only set this noticeably
#       higher if you're sure of the repercussions for sync workers.
#       For the non sync workers it just means that the worker
#       process is still communicating and is not tied to the length
#       of time required to handle a single request.
#
#   keepalive - The number of seconds to wait for the next request
#       on a Keep-Alive HTTP connection.
#
#       A positive integer. Generally set in the 1-5 seconds range.
#

workers = 1
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 2

#
#   spew - Install a trace function that spews every line of Python
#       that is executed when running the server. This is the
#       nuclear option.
#
#       True or False
#

spew = False

#
# Server mechanics
#
#   daemon - Detach the main Gunicorn process from the controlling
#       terminal with a standard fork/fork sequence.
#
#       True or False
#
#   raw_env - Pass environment variables to the execution environment.
#
#   pidfile - The path to a pid file to write
#
#       A path string or None to not write a pid file.
#
#   user - Switch worker processes to run as this user.
#
#       A valid user id (as an integer) or the name of a user that
#       can be retrieved with a call to pwd.getpwnam(value) or None
#       to not change the worker process user.
#
#   group - Switch worker process to run as this group.
#
#       A valid group id (as an integer) or the name of a user that
#       can be retrieved with a call to pwd.getgrnam(value) or None
#       to change the worker processes group.
#
#   umask - A mask for file permissions written by Gunicorn. Note that
#       this affects unix socket permissions.
#
#       A valid value for the os.umask(mode) call or a string
#       compatible with int(value, 0) (0 means Python guesses
#       the base, so values like "0", "0xFF", "0022" are valid
#       for decimal, hex, and octal representations)
#
#   tmp_upload_dir - A directory to store temporary request data when
#       requests are read. This will most likely be disappearing soon.
#
#       A path to a directory where the process owner can write. Or
#       None to signal that Python should choose one on its own.
#

daemon = False
raw_env = [
    'DJANGO_SECRET_KEY=something',
    'SPAM=eggs',
]
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

#
#   Logging
#
#   logfile - The path to a log file to write to.
#
#       A path string. "-" means log to stdout.
#
#   loglevel - The granularity of log output
#
#       A string of "debug", "info", "warning", "error", "critical"
#

errorlog = '-'
loglevel = 'info'
accesslog = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

#
# Process naming
#
#   proc_name - A base to use with setproctitle to change the way
#       that Gunicorn processes are reported in the system process
#       table. This affects things like 'ps' and 'top'. If you're
#       going to be running more than one instance of Gunicorn you'll
#       probably want to set a name to tell them apart. This requires
#       that you install the setproctitle module.
#
#       A string or None to choose a default of something like 'gunicorn'.
#

proc_name = None

#
# Server hooks
#
#   post_fork - Called just after a worker has been forked.
#
#       A callable that takes a server and worker instance
#       as arguments.
#
#   pre_fork - Called just prior to forking the worker subprocess.
#
#       A callable that accepts the same arguments as after_fork
#
#   pre_exec - Called just prior to forking off a secondary
#       master process during things like config reloading.
#
#       A callable that takes a server instance as the sole argument.
#

def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_fork(server, worker):
    load_model()

def pre_exec(server):
    server.log.info("Forked child, re-executing.")

def when_ready(server):
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    worker.log.info("worker received INT or QUIT signal")

    ## get traceback info
    import threading, sys, traceback
    id2name = {th.ident: th.name for th in threading.enumerate()}
    code = []
    for threadId, stack in sys._current_frames().items():
        code.append("\n# Thread: %s(%d)" % (id2name.get(threadId,""),
            threadId))
        for filename, lineno, name, line in traceback.extract_stack(stack):
            code.append('File: "%s", line %d, in %s' % (filename,
                lineno, name))
            if line:
                code.append("  %s" % (line.strip()))
    worker.log.debug("\n".join(code))

def worker_abort(worker):
    worker.log.info("worker received SIGABRT signal")
