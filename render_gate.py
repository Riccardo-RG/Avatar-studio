"""Defer new heavy jobs while the local director is active, without locking its audio."""
import time

def wait_for_live(director,cancelled,progress,sleep=time.sleep):
    waiting=False
    while True:
        if cancelled():raise ValueError('Produzione annullata.')
        if not director.running:raise ValueError('Studio chiuso prima dell’inizio della produzione.')
        with director.lock:
            blocked=director.phase in ('running','paused') and director.config.get('defer_render',True)
        if not blocked:return
        if not waiting:progress(0,'In coda fino alla fine della diretta. Copioni e post restano disponibili.');waiting=True
        sleep(.5)
