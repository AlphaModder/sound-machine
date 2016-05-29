import struct
import wave
import numpy
import bisect

from . import sd, SAMPLE_RATE, notes
from .signal import Signal

class Sound(Signal):
    pass

def play(thing, ret=False, blocking=True, length=None):
    duration = thing.duration if length is None else length * SAMPLE_RATE
    if duration == float('inf'):
        duration = 3*SAMPLE_RATE
    else:
        duration = int(duration)
    out = numpy.empty((duration, 1))
    for i in xrange(duration):
        out[i] = thing.amplitude(i)

    sd.play(out, blocking=blocking)
    if ret:
        return out

def play_async(thing):
    def cb(outdata, frames, time, status):
        startframe = stream.timer
        for i in xrange(frames):
            outdata[i] = thing.amplitude(i+startframe)
        stream.timer += frames
        if stream.timer >= thing.duration:
            raise sd.CallbackStop

    stream = sd.OutputStream(callback=cb)
    stream.timer = 0
    stream.start()
    return stream

def write(thing, filename):
    if thing.duration == float('inf'):
        raise ValueError("I can't write infinity to a file, numbnuts!")
    duration = int(thing.duration)
    mm = 2**15 - 1
    fp = wave.open(filename, 'w')
    fp.setparams((1, 2, 44100, 63822, 'NONE', 'not compressed'))
    fp.writeframes(''.join(struct.pack('h', int(max(min(thing.amplitude(i), 1), -1)*mm)) for i in xrange(duration)))
    fp.close()


class AsyncPlayer(Signal):
    def __init__(self):
        self.frame = 0
        self.pure = False
        self.duration = float('inf')
        self.playing = []
        self.infinite = []
        self.callbacks = []
        self.to_play = []

    def amplitude(self, frame):
        for n in self.to_play:
            self._play(n)
        self.to_play = []

        out = 0.
        self.frame = frame
        while len(self.callbacks) != 0 and frame >= -self.callbacks[-1][0]:
            _, callback = self.callbacks.pop()
            if callable(callback):
                callback()
            elif type(callback) is tuple:
                if len(callback) == 2 and callable(callback[0]):
                    callback[0](*callback[1])
                else:
                    self.play(*callback)
            else:
                self.play(callback)

        while len(self.playing) != 0 and frame >= -self.playing[-1][0]:
            self.playing.pop()

        for _, start, note in self.playing:
            out += note.amplitude(frame - start)
        for start, note in self.infinite:
            out += note.amplitude(frame - start)

        return out

    def _play(self, note):
        if note.duration == float('inf'):
            self.infinite.append((self.frame, note))
        else:
            end = self.frame + int(note.duration)
            bisect.insort(self.playing, (-end, self.frame, note))

    def play(self, note):
        self.to_play.append(note)

    def mute(self, note):
        i = 0
        while i < len(self.playing):
            if self.playing[i][2] == note:
                self.playing.pop(i)
            else:
                i += 1
        i = 0
        while i < len(self.infinite):
            if self.infinite[i][1] == note:
                self.infinite.pop(i)
            else:
                i += 1

    def queue(self, when, func, relative=True):
        if relative: when += self.frame
        bisect.insort(self.callbacks, (-when, func))

class KeyedAsyncPlayer(AsyncPlayer):
    def __init__(self):
        super(KeyedAsyncPlayer, self).__init__()
        self.active = {}

    def play(self, name, note):
        self.mute(name)
        self.active[name] = note
        super(KeyedAsyncPlayer, self).play(note)

    def mute(self, note):
        if note not in self.active:
            return
        super(KeyedAsyncPlayer, self).mute(self.active.pop(note))

class InstrumentPlayer(KeyedAsyncPlayer):
    def __init__(self, instrument):
        super(InstrumentInterface, self).__init__()
        self.instrument = instrument

    def play(self, note, *args, **kwargs):
        sig = self.instrument(note, *args, **kwargs)
        super(InstrumentPlayer, self).play(note, sig)

class GuitarStrummer(KeyedAsyncPlayer):
    def __init__(self, sample):
        super(GuitarStrummer, self).__init__()
        self.sample = sample

    chords = {
        'C': [0, 3, 2, 0, 1, 0],
        'Cm': [0, 0, 5, 5, 4, 3],
        'D': [None, 0, 0, 2, 3, 2],
        'Dm': [0, 0, 0, 2, 3, 2],
        'E': [0, 2, 2, 1, 0, 0],
        'Em': [0, 2, 2, 0, 0, 0],
        'F': [1, 3, 3, 2, 1, 1],
        'Fm': [0, 0, 3, 1, 1, 1],
        'G': [3, 2, 0, 0, 0, 3],
        'Gm': [0, 0, 5, 3, 3, 3],
        'A': [0, 0, 2, 2, 2, 0],
        'Am': [0, 0, 2, 2, 1, 0],
        'A7': [0, 0, 2, 0, 2, 0],
        'Am7': [0, 0, 2, 0, 1, 0],
        'B': [0, 0, 4, 4, 4, 2]
    }

    base_frequencies = map(notes.notename, ['E2', 'A2', 'D3', 'G3', 'B3', 'E4'])

    def strum_down(self, chord, delay=200):
        freqs = [None if n is None else 2**(n/12.)*b for n, b in zip(self.chords[chord], self.base_frequencies)]
        delays = [n * delay for n in xrange(6)]
        for i, (f, d) in enumerate(zip(freqs, delays)):
            if f is not None:
                self.queue(d, (i, self.sample(f)))

    def strum_up(self, chord, delay=200):
        freqs = [None if n is None else 2**(n/12.)*b for n, b in zip(self.chords[chord], self.base_frequencies)]
        delays = [n * delay for n in reversed(xrange(6))]
        for i, (f, d) in enumerate(zip(freqs, delays)):
            if f is not None:
                self.queue(d, (i, self.sample(f)))
            else:
                self.queue(d, (self.mute, (i,)))
    
