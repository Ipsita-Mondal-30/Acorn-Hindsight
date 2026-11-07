import threading
from concurrent.futures import ThreadPoolExecutor

from app.memory import HindsightMemory


class FakeClient:
    def __init__(self): self.threads = set()
    def _hit(self): self.threads.add(threading.get_ident())
    def create_bank(self, *a, **k): self._hit()
    def retain(self, *a, **k): self._hit()
    def retain_batch(self, *a, **k): self._hit()
    def delete_bank(self, *a, **k): self._hit()
    def recall(self, *a, **k):
        self._hit()
        class R: results = []
        return R()
    def reflect(self, *a, **k):
        self._hit()
        class R: text = "x"; based_on = None; structured_output = None
        return R()


def test_all_hindsight_calls_run_on_one_thread_even_from_many_request_threads():
    fc = FakeClient()
    m = HindsightMemory("t", client=fc)
    def work(i):
        m.ensure_bank(); m.retain("c", context="x", timestamp=None, tags=[], document_id=str(i))
        m.recall("q"); m.reflect("q")
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(work, range(16)))
    assert len(fc.threads) == 1 and threading.get_ident() not in fc.threads
