import json
import pytest
from personal_os.store import Store
from personal_os.governance import changes, effective, metadata
from personal_os.conversations import analysis_pack, list_sources
from personal_os.backup import create_backup, restore_backup
from test_dashboard import dashboard, request


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / 'vault'); s.init(); return s


def insight(s, source, title='结论', claim='inference', **kwargs):
    p = s.propose(title, title, '虚构测试', source_ids=[source['id']], claim_type=claim, **kwargs)
    s.review(p['proposal_id'], True)
    return s.get(p['record_id'])


@pytest.mark.parametrize('mode', ['source', 'deactivate', 'purge'])
def test_transitive_deletion_stops_reads_exports_and_proposals(store, mode):
    root = store.capture('原话', 'FORGET_SENTINEL')
    first = insight(store, root)
    second = insight(store, first, '第二层')
    pending = store.propose('待确认', 'FORGET_SENTINEL', '依据', source_ids=[second['id']])
    plan = store.deletion_preview(root['id'])
    assert {root['id'], first['id'], second['id'], pending['record_id']} == set(plan['affected_ids'])
    result = store.delete(root['id'], 1, mode, plan['impact'])
    assert result['external_cleanup_required'] and store.search() == []
    for r in [first, second]:
        with pytest.raises(ValueError): store.get(r['id'])
        with pytest.raises(ValueError): analysis_pack(store, [r['id']], '测试')
    if mode == 'purge':
        assert not store.proposals()
        assert not list((store.meta/'history').glob('*/*.md'))
        with pytest.raises(ValueError, match='Permanently'): store.restore(root['id'], 1)
        for file in store.root.rglob('*'):
            if file.is_file(): assert b'FORGET_SENTINEL' not in file.read_bytes()
    else:
        assert store.get(first['id'], include_inactive=True)['effective_state'] != 'active'
        with pytest.raises(ValueError, match='invalidated'): store.review(pending['proposal_id'], True)


def test_deletion_preview_rejects_new_dependents_and_missing_confirmation(store):
    root = store.capture('原话','演示'); p=store.deletion_preview(root['id'])
    insight(store, root)
    with pytest.raises(ValueError, match='impact changed'): store.delete(root['id'],1,'purge',p['impact'])
    with pytest.raises(ValueError, match='preview'): store.delete(root['id'],1,'purge')
    assert store.get(root['id'])


@pytest.mark.parametrize('memory,state', [({'valid_until':'2000-01-01T00:00:00Z'},'expired'),({'valid_from':'2099-01-01T00:00:00Z'},'not_yet_valid'),({'state':'inactive'},'inactive')])
def test_invalid_memories_excluded_everywhere(store, memory, state):
    r=store.capture('预算','虚构预算',memory=memory)
    assert store.search()==[] and list_sources(store)==[]
    assert store.get(r['id'],include_inactive=True)['effective_state']==state
    with pytest.raises(ValueError): store.get(r['id'])
    with pytest.raises(ValueError): analysis_pack(store,[r['id']],'预算')
    with pytest.raises(ValueError): store.propose('偏好','内容','理由',source_ids=[r['id']])


def test_expiring_or_changing_source_invalidates_approved_chain(store):
    root=store.capture('原话','原话'); first=insight(store,root); second=insight(store,first,'第二层')
    store.update_memory(root['id'],1,{'state':'inactive'})
    assert store.search()==[]
    assert store.get(first['id'],include_inactive=True)['effective_state']=='evidence_changed'
    assert store.get(second['id'],include_inactive=True)['effective_state']=='evidence_inactive'


@pytest.mark.parametrize('invalid', [{'scope':''},{'state':'expired'},{'valid_until':'2027-01-01'},{'valid_from':'2027-01-01T00:00:00Z','valid_until':'2026-01-01T00:00:00Z'},{'unknown':1}])
def test_metadata_validation(invalid):
    with pytest.raises(ValueError): metadata(invalid)


@pytest.mark.parametrize('resolution',['replace','keep_both','scoped'])
def test_conflict_requires_human_choice_preserves_comparison(store,resolution):
    root=store.capture('新证据','改了想法'); old=insight(store,root)
    p=store.propose('新结论','不同想法','冲突',old['id'],1,source_ids=[root['id']],claim_type='conflict')
    with pytest.raises(ValueError,match='resolution'): store.review(p['proposal_id'],True)
    store.review(p['proposal_id'],True,resolution,'2027 年工作场景' if resolution=='scoped' else None)
    rows=store.search(kind='profile'); assert len(rows)==(1 if resolution=='replace' else 2)
    reviewed=next(p for p in store.proposals() if p['state']=='approved' and p['record'].get('claim_type')=='conflict')['record']
    r=store.get(reviewed['id']); assert r['resolution']==resolution and r['claim_type']=='conflict'
    if resolution=='scoped': assert r['memory']['scope']=='2027 年工作场景'
    assert (store.meta/'history'/old['id']/'1.md').exists()


def test_decision_review_keeps_original_assumptions(store):
    original={'rationale':'当时的理由','conditions':'当时的预算','expected_outcome':'预期节省时间'}
    r=store.capture('虚构决策','购买计划','decision',memory=original)
    updated=store.update_memory(r['id'],1,{**original,'actual_outcome':'实际没有节省时间'})
    assert updated['memory']['reviewed_at'] and updated['memory']['rationale']==original['rationale']
    with pytest.raises(ValueError,match='original decision'): store.update_memory(r['id'],2,{'rationale':'事后改写'})
    with pytest.raises(ValueError,match='original decision'): store.propose('决策','改写','复盘',r['id'],2,'decision',memory={'rationale':'改写'})


def test_changes_paginate_and_hide_restricted_ids(store):
    secret=store.capture('秘密','秘密',sensitivity='restricted')
    for i in range(101): store.capture(str(i),'虚构')
    page=changes(store); assert page['has_more'] and secret['id'] not in json.dumps(page)
    next_page=changes(store,page['cursor']); assert not next_page['has_more']
    assert secret['id'] in json.dumps(changes(store,0,True))
    store.delete(secret['id'],1)
    assert secret['id'] not in json.dumps(changes(store,next_page['cursor']))


def test_restricted_impact_and_lifecycle_cannot_be_exposed(store):
    root=store.capture('秘密','秘密',sensitivity='restricted')
    with pytest.raises(ValueError,match='Restricted'): store.deletion_preview(root['id'])
    with pytest.raises(ValueError,match='Restricted'): store.update_memory(root['id'],1,{'state':'inactive'},False)


def test_later_restriction_hides_earlier_change_ids(store):
    r=store.capture('虚构','测试')
    p=store.propose('虚构','测试','收紧权限',r['id'],1,'record',sensitivity='restricted')
    store.review(p['proposal_id'],True)
    assert r['id'] not in json.dumps(changes(store,0))
    assert r['id'] in json.dumps(changes(store,0,True))


def test_backup_retains_revocation_and_change_feed(store):
    root=store.capture('原话','测试'); derived=insight(store,root)
    store.delete(root['id'],1)
    restored=restore_backup(store,create_backup(store))
    copy=Store(restored['restored_vault'])
    assert copy.search()==[] and changes(copy)['events']


def test_http_lifecycle_and_cascade(dashboard):
    store,address=dashboard
    root=store.capture('原话','测试'); derived=insight(store,root)
    assert request(address,'/governance.js').status==200
    plan=json.load(request(address,'/api/deletion-preview?id='+root['id']))
    result=json.load(request(address,'/api/delete',{'id':root['id'],'revision':1,'mode':'deactivate','impact':plan['impact']}))
    assert result['deleted']
    r=json.load(request(address,'/api/record?id='+derived['id'])); assert r['effective_state']!='active'
    data=json.load(request(address,'/api/snapshot')); assert data['records'][0]['effective_state']!='active'


def test_deletion_clears_old_import_previews(dashboard):
    from urllib.error import HTTPError
    store,address=dashboard
    root=store.capture('原话','测试')
    preview=json.load(request(address,'/api/import-preview',{'filename':'cache.txt','text':'CACHE_SENTINEL'}))
    plan=json.load(request(address,'/api/deletion-preview?id='+root['id']))
    request(address,'/api/delete',{'id':root['id'],'revision':1,'mode':'purge','impact':plan['impact']}).close()
    with pytest.raises(HTTPError):
        request(address,'/api/import-commit',{'preview_id':preview['preview_id'],'keys':[preview['items'][0]['key']]})
    assert store.search()==[]


def test_pending_import_cannot_publish_a_preview_after_delete(dashboard,monkeypatch):
    import threading
    import personal_os.dashboard as module
    from urllib.error import HTTPError
    store,address=dashboard
    root=store.capture('原话','测试'); plan=store.deletion_preview(root['id'])
    started,release=threading.Event(),threading.Event()
    original=module.parse_import
    def delayed(*args):
        started.set(); assert release.wait(5); return original(*args)
    monkeypatch.setattr(module,'parse_import',delayed)
    failures=[]
    def worker():
        try: request(address,'/api/import-preview',{'filename':'cache.txt','text':'虚构'})
        except HTTPError as e: failures.append(e.code)
    thread=threading.Thread(target=worker);thread.start();assert started.wait(5)
    try: request(address,'/api/delete',{'id':root['id'],'revision':1,'mode':'purge','impact':plan['impact']}).close()
    finally: release.set();thread.join(5)
    assert failures==[400]
