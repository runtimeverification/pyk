from __future__ import annotations

import threading

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar, final

from pyk.kast.inner import KApply, KSequence, KToken, KVariable, bottom_up_with_summary

if TYPE_CHECKING:
    from pyk.kast.inner import KInner, KLabel

A = TypeVar('A')


""" A lock optimized for a long sequence of reads followed by few writes.

The lock ensures that:
* Nobody is reading or writing while the write lock is acquired.
* No thread will wait forever in order to read or write (assuming that threads
  that acquire write locks also release them at some point, and that
  threads that acquire read locks either release them, or they try to acquire
  write locks).

Methods:
* The acquire_read() method should be called first, and it should not be
  called again.
* The acquire_write() method can be called multiple times without releasing.
* At the end, the user should call release(). Only one release call is needed
  regardless of how many acquire_* calls were made.

The lock should be used like this:

lock = ReadWriteLock()
lock.acquire_read()
try:
   read the locked object
   if there is a write:
      lock.acquire_write()
      write + read the logged object
finally:
  lock.release()

How it works:

Threads start by acquiring the read lock, and start reading.
Everyone can join until the first thread tries to acquire the write lock.
After this, everyone that wants to acquire the read lock gets blocked.
The thread that tries to acquire the write block also gets blocked.

As time passes, all threads that already acquired the read lock either finish
doing their job and release the read lock, or they try to acquire the write
lock and get blocked. When there are no more reading threads, one of the
threads waiting for the write lock wakes up. When it finishes its writing
and releases the lock, another writing thread wakes up, and so on.

When all writing threads finish, the threads that were trying to acquire the
reading lock wake up.

Internal invariant:

The invariant holds when threads are either outside the ReadWriteLock
methods, or blocked in the self.__lock.wait() calls:

* At most one thread has self.__thread_storage.state == ReadWriteLock.WRITE_LOCK

* self.__readers = count(thread; self.__thread_storage.state == ReadWriteLock.READ_LOCK)
* self.__writers_waiting = count(thread; self.__thread_storage.state == ReadWriteLock.WAIT_FOR_WRITE)
* bool2Int(self.__writer_running) = count(thread; self.__thread_storage.state == ReadWriteLock.WRITE_LOCK)

* self.__writer_running implies self.__readers == 0

* if self.__writers_waiting > 0 then self.__readers does not grow
"""
class ReadWriteLock:
    (NO_LOCK, READ_LOCK, WAIT_FOR_WRITE, WRITE_LOCK) = range(0, 3)
    def __init__(self) -> None:
        self.__lock = threading.Condition()
        self.__readers = 0
        self.__writers_waiting = 0
        self.__writer_running = False
        self.__thread_storage = threading.local()

    def acquire_read(self) -> None:
        self.__thread_storage.state = ReadWriteLock.NO_LOCK
        while True:
            with self.__lock:
                if self.__writers_waiting == 0 and not self.__writer_running:
                    self.__readers += 1
                    self.__thread_storage.state = ReadWriteLock.READ_LOCK
                    break
                self.__lock.wait()

    def acquire_write(self) -> None:
        if self.__thread_storage.state == ReadWriteLock.WRITE_LOCK:
            return
        if self.__thread_storage.state != ReadWriteLock.READ_LOCK:
            raise ValueError(f'Invalid lock state, perhaps read lock not acquired before write lock: {self.__thread_storage.state}')
        with self.__lock:
            self.__readers -= 1
            self.__writers_waiting += 1
            self.__thread_storage.state = ReadWriteLock.WAIT_FOR_WRITE
            self.__lock.notify_all()
        while True:
            with self.__lock:
                if self.__readers == 0 and not self.__writer_running:
                    self.__writers_waiting -= 1
                    self.__writer_running = True
                    self.__thread_storage.state = ReadWriteLock.WRITE_LOCK
                    break
                self.__lock.wait()

    def release(self) -> None:
        if self.__thread_storage.state == ReadWriteLock.WRITE_LOCK:
            with self.__lock:
                self.__writer_running = False
                self.__lock.notify_all()
        elif self.__thread_storage.state == ReadWriteLock.READ_LOCK:
            with self.__lock:
                self.__readers -= 1
                self.__lock.notify_all()
        else:
            raise ValueError(f'Invalid lock state, perhaps you did not start by acquiring the read lock. {self.__thread_storage.state}')
        self.__thread_storage.state = ReadWriteLock.NO_LOCK

    def has_write_lock(self) -> bool:
        return self.__thread_storage.state == ReadWriteLock.WRITE_LOCK

@dataclass
class CachedValues(Generic[A]):
    lock: ReadWriteLock
    value_to_id: dict[A, int] = field(default_factory=dict)
    values: list[A] = field(default_factory=list)

    def cache(self, value: A) -> int:
        id = self.value_to_id.get(value)
        if id is not None:
            return id
        self.lock.acquire_write()
        # Retry the search since the cache may have changed while
        # waiting for the lock.
        id = self.value_to_id.get(value)
        if id is not None:
            return id
        id = len(self.values)
        self.value_to_id[value] = id
        self.values.append(value)
        return id


@dataclass(eq=True, frozen=True)
class OptimizedKInner:
    @abstractmethod
    def build(self, klabels: list[KLabel], terms: list[KInner]) -> KInner:
        ...


@final
@dataclass(eq=True, frozen=True)
class SimpleOptimizedKInner(OptimizedKInner):
    term: KInner

    def build(self, klabels: list[KLabel], terms: list[KInner]) -> KInner:
        return self.term


@final
@dataclass(eq=True, frozen=True)
class OptimizedKApply(OptimizedKInner):
    label: int
    children: tuple[int, ...]

    def build(self, klabels: list[KLabel], terms: list[KInner]) -> KInner:
        return KApply(klabels[self.label], tuple(terms[child] for child in self.children))


@final
@dataclass(eq=True, frozen=True)
class OptimizedKSequence(OptimizedKInner):
    children: tuple[int, ...]

    def build(self, klabels: list[KLabel], terms: list[KInner]) -> KInner:
        return KSequence(tuple(terms[child] for child in self.children))


class KInnerOptimizer:
    def __init__(self) -> None:
        self.__lock: ReadWriteLock = ReadWriteLock()
        self.__optimized_terms: CachedValues[OptimizedKInner] = CachedValues(self.__lock)
        self.__klabels: CachedValues[KLabel] = CachedValues(self.__lock)

        self.__terms: list[KInner] = []

    def optimize(self, term: KInner) -> KInner:
        def optimizer(to_optimize: KInner, children: list[int]) -> tuple[KInner, int]:
            if isinstance(to_optimize, KToken) or isinstance(to_optimize, KVariable):
                optimized_id = self.cache(SimpleOptimizedKInner(to_optimize))
            elif isinstance(to_optimize, KApply):
                klabel_id = self.cache_klabel(to_optimize.label)
                optimized_id = self.cache(OptimizedKApply(klabel_id, tuple(children)))
            elif isinstance(to_optimize, KSequence):
                optimized_id = self.cache(OptimizedKSequence(tuple(children)))
            else:
                raise ValueError('Unknown term type: ' + str(type(to_optimize)))
            return (self.__terms[optimized_id], optimized_id)

        self.__lock.acquire_read()
        try:
            optimized, _ = bottom_up_with_summary(optimizer, term)
        finally:
            self.__lock.release()
        return optimized

    def cache(self, term: OptimizedKInner) -> int:
        id = self.__optimized_terms.cache(term)
        assert id <= len(self.__terms)
        if id == len(self.__terms):
            # The write lock should already be acquired by the
            # self.__optimized_terms.cache call above.
            assert self.__lock.has_write_lock()
            self.__terms.append(term.build(self.__klabels.values, self.__terms))
        return id

    def cache_klabel(self, label: KLabel) -> int:
        return self.__klabels.cache(label)
