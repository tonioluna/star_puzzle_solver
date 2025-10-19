import time
import inspect
import types
import os

_log = None

_perf_recorder = None
def get_perf_recorder():
    global _perf_recorder
    if _perf_recorder is None:
        _perf_recorder = Perf_Recorder()
    return _perf_recorder

def _fmt_time(t):
    m = int(t/60)
    return "%im %.3fs"%(m, t - m*60)

class Perf_Recorder:
    def __init__(self):
        self._events = []
        self._segment_durations = {}
        self._segment_hits = {}
        self._start_time = time.time()

    def record_checkpoint(self, id):
        e = types.SimpleNamespace()
        e.time = time.time()

        s = inspect.stack()
        e.call = "%s:%i %s()"%(os.path.basename(s[1].filename),
                               s[1].lineno,
                               s[1].function
                               )
        e.id = id

        d = _fmt_time(e.time - self._start_time)
        e.str = f"{'+'+d:>12}  {e.id:50}  {e.call}"
        _log.debug(e.str)
        
        self._events.append(e)
    
    def record_segment_accumulated_duration(self, segment_id, duration):
        if segment_id not in self._segment_durations:
            self._segment_durations[segment_id] = 0
            self._segment_hits[segment_id] = 0
        self._segment_durations[segment_id] += duration
        self._segment_hits[segment_id] += 1

    def dump(self):
        _log.info("Table of checkpoints")
        _log.info("-"*80)
        _log.info(f" {'time':12}  {'id':50}  {'call stack'}")
        _log.info("-"*80)
        for e in self._events:
            _log.info(e.str)
        _log.info("-"*80)
        if len(self._segment_durations) > 0:
            _log.info("")
            _log.info("Accumulated segment durations")
            _log.info("-"*80)
            _log.info(f" {'time':12}  {'%':>7}  {'Hits':>16}  {'segment'}")
            _log.info("-"*80)
            total_duration = sum(self._segment_durations.values())
            segment_durations = list(set(self._segment_durations.values()))
            segment_durations.sort(reverse=True)
            for seg_d in segment_durations:
                for s, d in self._segment_durations.items():
                    if seg_d == d:
                        _log.info(f" {_fmt_time(d):>12}  {100*d/total_duration:>6.1f}%  {self._segment_hits[s]:>16_}  {s}")
            _log.info("-"*80)
        
