"""Exercise the studio/platform lock order in a disposable child process."""
from pathlib import Path
import json
import subprocess
import sys
import textwrap
import unittest


class EditorialLockAuditTests(unittest.TestCase):
    def test_episode_save_and_campaign_to_plan_complete_concurrently(self):
        code = textwrap.dedent('''
            import json, tempfile, threading
            from pathlib import Path
            from unittest.mock import patch
            import studio, platform_store as store, agent_team

            a_in_snapshot = threading.Event()
            b_waiting_studio = threading.Event()
            errors = []

            class ObservedStudioLock:
                def __init__(self):
                    self.lock = threading.RLock()
                def __enter__(self):
                    if threading.current_thread().name == 'campaign-to-plan':
                        b_waiting_studio.set()
                    self.lock.acquire()
                    return self
                def __exit__(self, *args):
                    self.lock.release()

            with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'PATH', Path(tmp)/'studio.json'), patch.object(store, 'PATH', Path(tmp)/'platform.json'), patch.object(studio, 'LOCK', ObservedStudioLock()):
                c = store.save_campaign({'name':'Audit', 'topic':'Demo', 'audience':'Adults', 'objective':'Explain', 'character_id':'lumo', 'language':'en'})
                store.change_campaign(c['id'], lambda c: c['contents'].append({'id':'draft', 'title':'Demo', 'script':'A useful explanation.', 'status':'reviewed', 'character_id':'lumo', 'language':'en'}))
                studio.load()
                original_snapshot = store.snapshot

                def gated_snapshot(*args, **kwargs):
                    if threading.current_thread().name == 'episode-save':
                        a_in_snapshot.set()
                        if not b_waiting_studio.wait(2):
                            raise RuntimeError('Campaign did not attempt studio lock')
                    return original_snapshot(*args, **kwargs)

                def save_episode():
                    try:
                        studio.save_episode({'title':'Direct edit', 'script':'A different draft.', 'cover':'Demo', 'question':'Why?', 'character_id':'nova'})
                    except Exception as exc:
                        errors.append(str(exc))

                def to_plan():
                    try:
                        agent_team.to_plan({'campaign_id':c['id'], 'content_id':'draft'})
                    except Exception as exc:
                        errors.append(str(exc))

                with patch.object(store, 'snapshot', side_effect=gated_snapshot):
                    a = threading.Thread(target=save_episode, name='episode-save', daemon=True)
                    b = threading.Thread(target=to_plan, name='campaign-to-plan', daemon=True)
                    a.start()
                    if not a_in_snapshot.wait(2):
                        raise RuntimeError('Episode did not acquire studio lock')
                    b.start()
                    a.join(1)
                    b.join(1)
                    complete = not a.is_alive() and not b.is_alive()
                    report = {'complete': complete, 'errors': errors}
                    if complete:
                        item = store.find(store.load(), 'campaigns', c['id'])['contents'][0]
                        again = agent_team.to_plan({'campaign_id':c['id'], 'content_id':'draft'})
                        report['idempotent'] = again['episode_id'] == item['episode_id']
                        report['campaign_episode_count'] = sum(e['id'] == item['episode_id'] for e in studio.load()['episodes'])
                    print(json.dumps(report), flush=True)
        ''')
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).parent,
                                text=True, capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['complete'], 'Inverted lock order blocked both independent editorial saves')
        self.assertEqual(report['errors'], [])
        self.assertTrue(report['idempotent'])
        self.assertEqual(report['campaign_episode_count'], 1)


if __name__ == '__main__':
    unittest.main()
