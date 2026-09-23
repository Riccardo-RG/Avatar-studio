"""Offline research billing, localization and per-run paid-model consent."""
import copy
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import agent_team
import growth
import market_research as research
import platform_store as store
import providers
import web_sources


class ResearchTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        for target,name,value in [(store,'PATH',root/'platform.json'),(providers,'DATA',root),(growth,'PATH',root/'growth.json')]:
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)
        p=patch('socket.getaddrinfo',side_effect=AssertionError('Unexpected external network'))
        p.start();self.addCleanup(p.stop)
        self.c=store.save_campaign({'name':'Ricerca','topic':'Ordine digitale','audience':'Studenti','objective':'Confrontare due aperture','character_id':'lumo','budget_eur':10,'research_queries':3})
        store.save_budget({'budget_eur':30,'brave_eur_query':.005})
        self.source={'url':'https://example.com/source','title':'Fonte','excerpt':'Una fonte di prova sufficientemente lunga per il contesto editoriale.'}

    def test_plan_is_read_only_and_prices_every_query(self):
        before=store.PATH.read_bytes()
        with patch.dict(os.environ,{'BRAVE_SEARCH_API_KEY':'test'}),patch.object(web_sources,'search') as search:
            plan=research.plan({'campaign_id':self.c['id']})
        self.assertEqual(plan['estimated_eur'],.015);self.assertEqual(len(plan['queries']),3)
        self.assertTrue(plan['configured']);search.assert_not_called();self.assertEqual(store.PATH.read_bytes(),before)

    def test_all_supported_locales_propagate_to_search(self):
        for language in ('it','en','es'):
            for country in research.COUNTRIES:
                c={**self.c,'language':language,'research_country':country}
                with patch.object(web_sources,'search',return_value=[self.source]) as search:
                    sources,executed=research.execute(c,lambda:False)
                self.assertEqual(len(executed),3);self.assertEqual(sources,[self.source])
                for call in search.call_args_list:self.assertEqual(call.kwargs,{'language':language,'country':country})

    def test_invalid_research_choices_never_search(self):
        with patch.object(web_sources,'search') as search:
            for fields in ({'language':'fr'},{'research_country':'ZZ'},{'research_queries':True},{'research_queries':4}):
                with self.assertRaises(ValueError):research.execute({**self.c,**fields},lambda:False)
            search.assert_not_called()

    def test_stop_between_queries_prevents_further_costs(self):
        stop=threading.Event()
        def search(*args,**kwargs):stop.set();return [self.source]
        with patch.object(web_sources,'search',side_effect=search) as fetch:
            sources,executed=research.execute(self.c,stop.is_set)
        self.assertEqual(fetch.call_count,1);self.assertEqual(len(executed),1);self.assertEqual(sources,[self.source])

    def test_search_bills_each_actual_request_and_sends_country_language(self):
        response={'web':{'results':[{'url':self.source['url'],'title':'Fonte','description':'Estratto'}]}}
        with patch.dict(os.environ,{'BRAVE_SEARCH_API_KEY':'test'}),patch.object(web_sources.runtime_config,'ssl_context',return_value=None),patch('urllib.request.urlopen',side_effect=lambda *a,**k:BytesIO(json.dumps(response).encode())) as http:
            research.execute({**self.c,'language':'es','research_country':'MX'},lambda:False)
        self.assertEqual(http.call_count,3);self.assertAlmostEqual(store.budget_summary()['reserved_eur'],.015)
        for call in http.call_args_list:
            q=parse_qs(urlparse(call.args[0].full_url).query)
            self.assertEqual(q['country'],['MX']);self.assertEqual(q['search_lang'],['es'])

    def test_failed_query_keeps_reservation_and_stops_remaining_queries(self):
        with patch.dict(os.environ,{'BRAVE_SEARCH_API_KEY':'test'}),patch.object(web_sources.runtime_config,'ssl_context',return_value=None),patch('urllib.request.urlopen',side_effect=OSError('offline')) as http:
            with self.assertRaises(ValueError):research.execute(self.c,lambda:False)
        self.assertEqual(http.call_count,1);self.assertAlmostEqual(store.budget_summary()['reserved_eur'],.005)

    def test_missing_key_or_zero_budget_never_contacts_service(self):
        with patch.dict(os.environ,{},clear=True),patch('urllib.request.urlopen') as http:
            with self.assertRaises(ValueError):web_sources.search('test',self.c['id'])
            http.assert_not_called()
        store.save_budget({'budget_eur':0})
        with patch.dict(os.environ,{'BRAVE_SEARCH_API_KEY':'test'}),patch('urllib.request.urlopen') as http:
            with self.assertRaises(ValueError):web_sources.search('test',self.c['id'])
            http.assert_not_called()

    def test_generated_queries_respect_brave_word_limit(self):
        c={**self.c,'topic':'a '*250,'audience':'b '*250}
        self.assertTrue(all(len(q.split())<=75 and len(q)<=500 for q in research.queries(c)))

    def run_team(self,role,allow_paid=False,provider='openai'):
        c={**copy.deepcopy(self.c),'sources':[self.source]}
        run={'id':'research-test','role':role,'steps':[],'status':'queued','brief_revision':c['revision'],'allow_paid':allow_paid}
        store.change_campaign(c['id'],lambda current:current['runs'].append(copy.deepcopy(run)))
        with patch.object(providers,'settings',return_value={**providers.DEFAULTS,'provider':provider}):
            agent_team.work(c['id'],c,run,threading.Event(),False)
        return run

    def test_paid_team_stops_before_models_without_consent(self):
        with patch.object(providers,'agent_text') as strategist,patch.object(providers,'generate_script') as writer:
            run=self.run_team('all')
        self.assertEqual(run['status'],'error');self.assertIn('consenti',run['message'])
        strategist.assert_not_called();writer.assert_not_called()

    def test_paid_team_consent_is_honored_for_one_run_only(self):
        with patch.object(providers,'agent_text',return_value='Una strategia da rivedere.') as model:
            first=self.run_team('strategy',True);second=self.run_team('strategy',False)
        self.assertEqual(first['status'],'done');self.assertEqual(second['status'],'error');self.assertEqual(model.call_count,1)

    def test_local_team_does_not_require_paid_consent(self):
        with patch.object(providers,'agent_text',return_value='Una strategia locale.'):
            self.assertEqual(self.run_team('strategy',provider='local')['status'],'done')

    def test_non_boolean_opt_ins_never_schedule_a_worker(self):
        with patch.object(agent_team.POOL,'submit') as submit:
            for field in ('allow_paid','search_web'):
                for value in ('false','true',1,[],None):
                    with self.assertRaises(ValueError):agent_team.start({'campaign_id':self.c['id'],field:value})
            submit.assert_not_called()

    def test_macos_voice_catalog_deduplicates_localized_names(self):
        import media
        media.voice_catalog.cache_clear();self.addCleanup(media.voice_catalog.cache_clear)
        with patch.object(media.subprocess,'check_output',return_value='Alice (Italiano) it_IT # Ciao\nAlice (Italiano) it_IT # Ciao\nDaniel en_GB # Hello'):
            rows=media.voice_catalog()
        self.assertEqual(sum(v['id']=='Alice (Italiano)' for v in rows),1)


if __name__=='__main__':unittest.main()
