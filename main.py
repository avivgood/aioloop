import datetime
import selectors
from collections import deque
from datetime import timedelta
from selectors import EpollSelector, EVENT_READ, DefaultSelector
from typing import Awaitable, Callable, Iterable, Iterator, Tuple
import heapq
import time
import socket
from selectors import EVENT_WRITE, EVENT_READ
from typing import Tuple


class HTTPClient:
    def __init__(self, host: str, port: int = 80):
        self.host = host
        self.port = port
        self.sock = None

    async def connect(self):
        """Connect to the server and wait for the socket to be writable."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(False)
        try:
            self.sock.connect((self.host, self.port))
        except BlockingIOError:
            pass

        # Wait for the socket to be writable
        await Fut(self.sock.fileno(), EVENT_WRITE)

    async def send_request(self, request: str):
        """Send the HTTP request and wait for the socket to be writable."""
        await Fut(self.sock.fileno(), EVENT_WRITE)
        self.sock.sendall(request.encode('utf-8'))

    async def read_response(self) -> str:
        """Read the response from the server."""
        response = []
        while True:
            await Fut(self.sock.fileno(), EVENT_READ)
            chunk = self.sock.recv(4096)  # Read up to 4096 bytes
            if not chunk:
                break
            response.append(chunk.decode('utf-8'))
        return ''.join(response)

    async def get(self, path: str) -> str:
        """Perform an HTTP GET request."""
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            f"Connection: close\r\n\r\n"
        )
        await self.connect()
        await self.send_request(request)
        response = await self.read_response()
        self.sock.close()
        return response

# Test the HTTP client
async def test_http_client(i):
    print(f"({i}) - start ")
    client = HTTPClient("oopop.free.beeceptor.com", 80)
    response = await client.get("/")
    print(f"({i}): " +  response)


class Fut:
    def __init__(self,
                 fd: int,
                 event: int,
                 ):
        self.fd = fd
        self.event = event

    def __await__(self):
        yield self


class Sleep:
    def __init__(self, amount: float):
        self.amount = amount

    def __await__(self):
        yield self


class Gather:
    def __init__(self, wait: list[Awaitable]):
        self.wait = wait

    def __await__(self):
        yield self


class GatherSync:
    def __init__(self, tasks_to_do: int, original_iterator: Iterator):
        self.__tasks_to_do = tasks_to_do
        self.__original_iterator = original_iterator

    def mark_task_done(self):
        self.__tasks_to_do = self.__tasks_to_do - 1

    def are_all_tasks_done(self):
        return self.__tasks_to_do == 0

    def original_iterator(self):
        return self.__original_iterator


class GatherIter:
    def __init__(self, gather_sync: GatherSync, it: Iterator):
        self.gather_sync = gather_sync
        self.it = it

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.it)


async def test():
    print("hi")
    await Sleep(5)
    print("bye")

async def test1(i):
    print("hi" + str(i))
    await Sleep(3)
    print("bye" + str(i))

async def test2():
    await Gather([test(), test1()])

async def make_http_network_request():
    pass


def run(a: Awaitable):
    q: deque[Iterator] = deque()
    sleepers: list[tuple[datetime, Iterator]] = []
    io = selectors.DefaultSelector()
    q.append(a.__await__())
    while len(q) != 0 or io.get_map() != {} or len(sleepers) != 0:
        while len(q) != 0:
            a = q.popleft()
            try:
                n = next(a)
            except StopIteration:
                if isinstance(a, GatherIter):
                    a.gather_sync.mark_task_done()
                    if a.gather_sync.are_all_tasks_done():
                        q.append(a.gather_sync.original_iterator())
            else:
                if isinstance(n, Gather):
                    tasks = list(n.wait)
                    if len(tasks) == 0:
                        q.append(a)
                    sync = GatherSync(len(tasks), a)
                    for item in tasks:
                        q.append(GatherIter(sync, item.__await__()))
                elif isinstance(n, Sleep):
                    heapq.heappush(sleepers,
                                   (datetime.datetime.now() +
                                    timedelta(seconds=n.amount), a))
                elif isinstance(n, Fut):
                    io.register(n.fd, n.event, a)
                elif isinstance(n, Awaitable):
                    q.append(n.__await__())
                    q.append(a)
                else:
                    q.append(a)
        while len(sleepers) > 0 and sleepers[0][0] < datetime.datetime.now():
            item = heapq.heappop(sleepers)
            q.append(item[1])
        if io.get_map() == {}:
            if len(q) == 0 and len(sleepers) != 0 and sleepers[0][0] > datetime.datetime.now():
                t = (sleepers[0][0] - datetime.datetime.now()).total_seconds()
                time.sleep(t)

            continue

        if len(q) != 0 or (len(sleepers) != 0 and sleepers[0][0] <= datetime.datetime.now()):
            io_events = io.select(0)
        elif len(sleepers) != 0:
            f: datetime = sleepers[0][0]
            io_events = io.select((f - datetime.datetime.now()).total_seconds())
        else:
            io_events = io.select()

        for selector_key, fd in io_events:
            io.unregister(selector_key.fd)
            q.append(selector_key.data)


run(Gather([test_http_client(i) for i in range(50)] + [test1(i) for i in range(50)]))
