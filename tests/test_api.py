import gzip
from fastapi.testclient import TestClient
from race.app import Provider, create_app
from race.contracts import Agent, Decision
from race.settings import Settings


class FixedBrain:
    async def choose(self, context):
        return Decision(context.candidates[0].id,"fixture")


def make_client(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "index.html").write_text("<html>fixture</html>")
    (game / "index.wasm").write_bytes(b"wasm-fixture")
    (game / "index.wasm.gz").write_bytes(gzip.compress(b"wasm-fixture"))
    return TestClient(create_app(Settings(web_dir=game), {
        "jev":Provider("Jev fixture",lambda token:Agent(FixedBrain()))}))


def test_no_credentials_or_history_are_persisted(tmp_path,monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY","must-not-be-used")
    with make_client(tmp_path) as client:
        payload=dict(seed=42,count=4,event_id=0,energy=3)
        assert client.post('/api/decide',json=payload).status_code == 401
        result=client.post('/api/decide',json=payload,
                           headers={'Authorization':'Bearer fixture-secret-token'})
        assert result.json()['status']=='ok'
        assert 'fixture-secret-token' not in result.text
        assert result.headers['cache-control']=='no-store'
        assert 'set-cookie' not in result.headers
        assert not client.cookies
        for path in ['/api/matches','/api/race/matches','/race/report/anything']:
            assert client.get(path).status_code == 404
    assert not list(tmp_path.rglob('*.sqlite*'))


def test_validation_never_echoes_a_misplaced_secret(tmp_path):
    with make_client(tmp_path) as client:
        result=client.post('/api/track',json={'seed':42,'count':4,'token':'private-value'})
        assert result.status_code==422
        assert 'private-value' not in result.text
        assert client.post('/api/track',json={'seed':42,'count':True}).status_code==422
        assert client.post('/api/track',json={'seed':42,'count':41}).status_code==400
        assert client.post('/api/track',content=b' ' * 8193).status_code==413


def test_web_delivery_and_no_cors_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response=client.get('/game/index.wasm',headers={'Accept-Encoding':'gzip'})
        assert response.content==b'wasm-fixture'
        assert response.headers['content-encoding']=='gzip'
        assert response.headers['content-type']=='application/wasm'
        raw=client.get('/game/index.wasm',headers={'Accept-Encoding':'gzip;q=0'})
        assert 'content-encoding' not in raw.headers
        response=client.get('/',headers={'Origin':'https://unrelated.invalid'})
        assert 'access-control-allow-origin' not in response.headers
        assert 'wasm-unsafe-eval' in response.headers['content-security-policy']
        assert response.headers['cache-control']=='no-store'
