"""Fair job queue for the AI workers.

One queue per owner (a run). Free workers take jobs round-robin across the runs, and no run has more
than `per_owner` jobs in flight, so a run of 100 sections does not hold up the person who started
one after it. The AI calls are I/O-bound (streamed HTTP), so plain threads are enough.
"""
import threading
import traceback
from collections import OrderedDict, deque


class Scheduler:
    def __init__(self, workers, per_owner):
        self.workers = max(1, workers)
        self.per_owner = max(1, per_owner)
        self._cv = threading.Condition()
        self._queues = OrderedDict()  # owner → deque of (key, fn, args); the front owner is served next
        self._running = {}  # owner → jobs in flight
        self._keys = set()  # keys of queued jobs: the same job is never queued twice
        for i in range(self.workers):
            threading.Thread(target=self._work, name=f"ai-worker-{i}", daemon=True).start()

    def submit(self, owner, key, fn, *args):
        """Queue fn(*args). Returns False if a job with this key is already waiting in the queue."""
        with self._cv:
            if key in self._keys:
                return False
            self._keys.add(key)
            self._queues.setdefault(owner, deque()).append((key, fn, args))
            self._cv.notify()
        return True

    def cancel(self, owner):
        """Drop the owner's queued jobs (running ones finish on their own). Returns how many were dropped."""
        with self._cv:
            q = self._queues.pop(owner, None) or ()
            for key, _, _ in q:
                self._keys.discard(key)
            return len(q)

    def position(self, owner):
        """{queued, running, ahead}: ahead = runs served before this one's next job."""
        with self._cv:
            order = [o for o in self._queues if self._running.get(o, 0) < self.per_owner]
            q = self._queues.get(owner) or ()
            return {"queued": len(q), "running": self._running.get(owner, 0),
                    "ahead": order.index(owner) if q and owner in order else 0}

    def stats(self):
        with self._cv:
            return {"workers": self.workers, "per_run": self.per_owner, "running": sum(self._running.values()),
                    "queued": sum(len(q) for q in self._queues.values()), "runs": len(set(self._queues) | set(self._running))}

    def _next(self):
        for owner, q in self._queues.items():
            if self._running.get(owner, 0) < self.per_owner:
                job = q.popleft()
                if q:
                    self._queues.move_to_end(owner)  # round-robin: this run goes to the back
                else:
                    del self._queues[owner]
                self._running[owner] = self._running.get(owner, 0) + 1
                self._keys.discard(job[0])
                return owner, job
        return None

    def _work(self):
        while True:
            with self._cv:
                nxt = self._next()
                while nxt is None:
                    self._cv.wait()
                    nxt = self._next()
            owner, (_, fn, args) = nxt
            try:
                fn(*args)
            except Exception:  # noqa: BLE001 — a failing job must not take its worker down
                traceback.print_exc()
            finally:
                with self._cv:
                    self._running[owner] -= 1
                    if not self._running[owner]:
                        del self._running[owner]
                    self._cv.notify_all()  # a capped run may have a free slot now
