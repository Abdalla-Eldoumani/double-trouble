"""No live credentials or paid calls: real SDK contracts with mocked endpoints."""
import copy
import io
import subprocess
import types
import wave
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import briefing, planning, ui
from engine.agent import run
from engine.planner import parse

ROOT = Path(__file__).resolve().parent.parent


def wav(seconds=0.2, value=100):
    data = io.BytesIO()
    with wave.open(data, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(value.to_bytes(2, 'little', signed=True) * int(seconds * 16000))
    return data.getvalue()


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    st.cache_data.clear()
    for name in ('ELEVENLABS_API_KEY', 'ELEVENLABS_VOICE_ID', 'ELEVENLABS_TTS_MODEL_ID', 'ELEVENLABS_STT_MODEL_ID'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(briefing.st, 'secrets', {})
    yield
    st.cache_data.clear()


@pytest.fixture
def sdk(monkeypatch):
    calls = {'stt': [], 'tts': [], 'clients': []}
    calls['transcript'] = 'Show the top 20 locations in northeast Calgary.'
    calls['failure'] = None

    class Client:
        def __init__(self, **kwargs):
            calls['clients'].append(kwargs)
            self.speech_to_text = types.SimpleNamespace(convert=self.stt)
            self.text_to_speech = types.SimpleNamespace(convert=self.tts)

        def stt(self, **kwargs):
            calls['stt'].append(kwargs)
            if calls['failure']:
                raise calls['failure']
            return types.SimpleNamespace(text=calls['transcript'])

        def tts(self, **kwargs):
            calls['tts'].append(kwargs)
            if calls['failure']:
                raise calls['failure']
            return iter([b'ID3', b'mocked audio'])

    monkeypatch.setattr('elevenlabs.client.ElevenLabs', Client)
    return calls


def app():
    at = AppTest.from_file(str(ROOT / 'app/main.py'), default_timeout=60).run()
    assert not at.exception, at.exception
    return at


def click(at, key):
    at.button(key=key).click().run()
    assert not at.exception, at.exception


def open_voice(at, monkeypatch, data=None):
    # AppTest cannot upload into audio_input. Substitute only that widget's
    # return value; real buttons, review form, callbacks and planner still run.
    holder = {'data': data}
    monkeypatch.setattr(st, 'audio_input', lambda *a, **kw: io.BytesIO(holder['data']) if holder['data'] is not None else None)
    at.toggle(key='voice_open').set_value(True).run()
    assert not at.exception, at.exception
    return holder


def summary(at):
    return next(n.proto.body for n in at.get('html') if 'class="dt recommendation-summary"' in n.proto.body)


def apply_voice(at, text):
    at.text_area(key='voice_transcript').set_value(text)
    next(b for b in at.button if b.label == 'Apply request').click().run()
    assert not at.exception, at.exception


def test_environment_precedence_and_safe_missing_secrets(monkeypatch):
    monkeypatch.setattr(briefing.st, 'secrets', {'ELEVENLABS_API_KEY': 'secret-file-test-key'})
    assert briefing.api_key() == 'secret-file-test-key'
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'env-test-key')
    assert briefing.api_key() == 'env-test-key'
    monkeypatch.delenv('ELEVENLABS_API_KEY')

    class Missing:
        def get(self, name):
            raise FileNotFoundError('missing')
    monkeypatch.setattr(briefing.st, 'secrets', Missing())
    assert briefing.api_key() is None
    assert briefing.speech_config()['stt_model'] == 'scribe_v2'


def test_optional_configuration_and_placeholder(monkeypatch):
    monkeypatch.setattr(briefing.st, 'secrets', {'ELEVENLABS_VOICE_ID': 'file-voice'})
    assert briefing.speech_config()['voice_id'] == 'file-voice'
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'env-voice')
    monkeypatch.setenv('ELEVENLABS_TTS_MODEL_ID', 'eleven_flash_v2_5')
    monkeypatch.setenv('ELEVENLABS_STT_MODEL_ID', 'scribe_v1')
    assert briefing.speech_config() == {'voice_id': 'env-voice', 'tts_model': 'eleven_flash_v2_5', 'stt_model': 'scribe_v1'}
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'paste-your-key-here')
    assert briefing.api_key() is None


def test_sdk_contracts_no_retries_and_chunked_audio(sdk):
    data = wav()
    assert briefing.transcribe(data, 'mock-key') == sdk['transcript']
    sent = sdk['stt'][0]
    assert sent['file'] == ('request.wav', data, 'audio/wav')
    assert sent['model_id'] == 'scribe_v2' and sent['language_code'] == 'eng'
    assert sent['tag_audio_events'] is False and sent['diarize'] is False
    assert sent['request_options'] == {'max_retries': 0, 'timeout_in_seconds': 30}
    assert briefing.synthesize('Current briefing.', 'mock-key') == b'ID3mocked audio'
    assert sdk['tts'][0]['output_format'] == 'mp3_44100_128'
    assert sdk['tts'][0]['model_id'] == 'eleven_multilingual_v2'
    assert all(c['timeout'] == 30 for c in sdk['clients'])


@pytest.mark.parametrize('data', [b'', b'not WAV', wav(0), wav(0.05), wav(91)])
def test_unusable_audio_never_calls_api(sdk, data):
    with pytest.raises(briefing.SpeechError):
        briefing.transcribe(data, 'mock-key')
    assert not sdk['clients']


def test_blank_transcript_and_empty_tts_are_safe(sdk, monkeypatch):
    sdk['transcript'] = '  '
    with pytest.raises(briefing.SpeechError, match='No speech'):
        briefing.transcribe(wav(), 'mock-key')
    monkeypatch.setattr(briefing, '_client', lambda key: types.SimpleNamespace(text_to_speech=types.SimpleNamespace(convert=lambda **kw: iter([]))))
    with pytest.raises(briefing.SpeechError, match='No summary audio'):
        briefing.synthesize('test', 'mock-key')


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_sdk_errors_do_not_expose_key_or_request(sdk, status):
    exc = RuntimeError('sensitive-key and private-request details')
    exc.status_code = status
    sdk['failure'] = exc
    for action in (lambda: briefing.transcribe(wav(), 'sensitive-key'), lambda: briefing.synthesize('private-request', 'sensitive-key')):
        with pytest.raises(briefing.SpeechError) as captured:
            action()
        assert 'sensitive-key' not in str(captured.value)
        assert 'private-request' not in str(captured.value)
        assert captured.value.__suppress_context__


def test_missing_key_app_and_typed_planner_work(sdk, monkeypatch):
    at = app()
    assert at.button(key='read_summary').disabled
    open_voice(at, monkeypatch)
    assert at.button(key='transcribe_recording').disabled
    assert 'Typed planning works without a key' in ' '.join(c.value for c in at.caption)
    at.text_input(key='planner_text').set_value('Top 5 in northeast Calgary.')
    next(b for b in at.button if b.label == 'Update recommendations').click().run()
    assert not at.exception
    assert at.selectbox(key='area').value == 'NE'
    assert at.number_input(key='capacity').value == 5
    assert not sdk['clients']


def test_review_edit_same_planner_followups_and_no_duplicate_stt(sdk, monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'mock-key')
    at = app()
    before = copy.deepcopy(at.session_state['last_result'])
    open_voice(at, monkeypatch, wav())
    assert not sdk['clients']  # recording and opening alone do nothing
    click(at, 'transcribe_recording')
    assert at.text_area(key='voice_transcript').value == sdk['transcript']
    assert at.session_state['last_result'] == before  # review required
    at.text_area(key='voice_transcript').set_value('Top five locations in northwest Calgary. Give recent crashes twice the importance.')
    at.toggle(key='dark_mode').set_value(True).run()
    assert 'northwest Calgary' in at.text_area(key='voice_transcript').value
    at.run()
    assert len(sdk['stt']) == 1 and not sdk['tts']
    assert at.button(key='transcribe_recording').disabled
    apply_voice(at, at.text_area(key='voice_transcript').value)
    assert at.selectbox(key='area').value == 'NW'
    assert at.number_input(key='capacity').value == 5
    assert at.slider(key='recent_weight').value == 2
    assert '5 locations recommended in Northwest Calgary' in summary(at)
    apply_voice(at, 'Now show all Calgary.')
    assert at.selectbox(key='area').value == 'ALL'
    assert at.number_input(key='capacity').value == 5
    at.selectbox(key='priorities').select('Pedestrians and cyclists').run()
    at.number_input(key='capacity').set_value(10).run()
    at.toggle(key='dark_mode').set_value(False).run()
    assert at.selectbox(key='area').value == 'ALL'
    assert len(sdk['stt']) == 1 and not sdk['tts']
    assert at.session_state['settings'] == planning.from_result(at.session_state['last_result'])
    at.toggle(key='voice_open').set_value(False).run()
    at.toggle(key='voice_open').set_value(True).run()
    assert at.text_area(key='voice_transcript').value == 'Now show all Calgary.'


def test_new_recording_and_deliberate_retry(sdk, monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'mock-key')
    at = app()
    holder = open_voice(at, monkeypatch, wav())
    sdk['failure'] = RuntimeError('sensitive-key private-request')
    click(at, 'transcribe_recording')
    assert at.warning and not at.button(key='transcribe_recording').disabled
    assert 'sensitive-key' not in at.warning[0].value
    at.toggle(key='dark_mode').set_value(True).run()
    assert len(sdk['stt']) == 1
    sdk['failure'] = None
    click(at, 'transcribe_recording')
    assert len(sdk['stt']) == 2
    holder['data'] = wav(value=200)
    at.run()
    assert at.text_area(key='voice_transcript').value == ''
    assert not at.button(key='transcribe_recording').disabled
    click(at, 'transcribe_recording')
    assert len(sdk['stt']) == 3
    holder['data'] = None
    at.run()
    holder['data'] = wav(value=200)
    at.run()
    assert at.text_area(key='voice_transcript').value == sdk['transcript']
    assert at.button(key='transcribe_recording').disabled and len(sdk['stt']) == 3


def test_current_summary_audio_dedup_theme_and_stale_invalidation(sdk, monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'mock-key')
    at = app()
    assert not at.get('audio') and not sdk['clients']
    click(at, 'read_summary')
    script = sdk['tts'][0]['text']
    assert script == briefing.build_script(at.session_state['last_result'])
    assert 'All Calgary' in script and '20 locations' in script
    assert len(script.split()) <= 105
    assert len(at.get('audio')) == 1 and not at.get('audio')[0].proto.autoplay
    saved = copy.deepcopy(at.session_state['summary_audio'])
    at.toggle(key='dark_mode').set_value(True).run()
    at.run()
    click(at, 'read_summary')
    assert len(sdk['tts']) == 1 and at.session_state['summary_audio'] == saved
    at.selectbox(key='area').select('NE').run()
    assert not at.get('audio') and 'summary_audio' not in at.session_state
    click(at, 'read_summary')
    assert len(sdk['tts']) == 2 and 'Northeast Calgary' in sdk['tts'][-1]['text']
    at.checkbox(key='exclude_provincial').uncheck().run()
    assert not at.get('audio')
    click(at, 'read_summary')
    assert 'Deerfoot and Stoney included' in sdk['tts'][-1]['text']
    at.selectbox(key='priorities').select('Pedestrians and cyclists').run()
    assert not at.get('audio')
    assert not at.expander[0].proto.expanded


def test_tts_failure_retry_and_unsupported_voice_keep_app_usable(sdk, monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'mock-key')
    at = app()
    sdk['failure'] = RuntimeError('sensitive-key private-request')
    click(at, 'read_summary')
    assert at.warning and not at.get('audio')
    at.run()
    assert len(sdk['tts']) == 1
    sdk['failure'] = None
    click(at, 'read_summary')
    assert len(sdk['tts']) == 2 and at.get('audio')
    open_voice(at, monkeypatch)
    before = copy.deepcopy(at.session_state['last_result'])
    apply_voice(at, 'What is the weather like?')
    assert at.session_state['last_result'] == before
    assert at.session_state['reply']['text'].startswith('Settings unchanged.')
    apply_voice(at, '   ')
    assert at.warning and at.session_state['last_result'] == before
    apply_voice(at, 'Now show all Calgary.')
    assert not at.warning


def test_briefing_is_current_factual_and_invalidates_unspoken_rows():
    result = run({'w_severity': 1.0, 'w_trend': 0.5}, tune=False, constraints={'region': 'NE', 'budget': 5, 'recent_weight': 2})
    script = briefing.build_script(result)
    assert 'Northeast Calgary, 5 locations' in script
    assert 'pedestrian, cyclist, multi-vehicle and blocked-lane reports' in script
    assert 'weighted 2 times' in script and 'excluded by location name' in script
    assert 'severity points' not in script and 'Backtest' not in script
    assert 'reported 2025 crashes' in script and len(script.split()) <= 105
    rows = ui.recommended_rows(result)
    assert briefing.spoken_name(rows[0]['name']) in script
    assert f"{rows[0]['incidents']} reported crashes" in script
    cfg = briefing.speech_config()
    first = briefing.briefing_id(result, cfg)
    changed = copy.deepcopy(result)
    changed['top20'][4]['incidents'] += 1
    assert briefing.briefing_id(changed, cfg) != first
    assert briefing.briefing_id(result, {**cfg, 'voice_id': 'different'}) != first
    result['plan']['shortlist'] = []
    assert '0 locations' in briefing.build_script(result)
    assert 'No locations qualify' in briefing.build_script(result)


@pytest.mark.parametrize('phrase,field,value', [
    ('Show the top 20 locations in northeast Calgary.', 'constraints', {'budget': 20, 'region': 'NE'}),
    ('Give pedestrian and cyclist crashes more importance.', 'weights', {'w_severity': 1.0}),
    ('Exclude Deerfoot and Stoney Trail.', 'weights', {'exclude_provincial': True}),
    ('Now show all Calgary.', 'constraints', {'region': None}),
    ('Find the best ranking automatically.', 'tune', True),
])
def test_voice_examples_are_supported(phrase, field, value):
    assert parse(phrase)[field] == value


def test_secret_files_ignored_and_example_trackable():
    names = ['.streamlit/secrets.toml', '.env', '.env.local', '.env.production', 'operator.local.env', 'secrets.env', 'operator.env.local']
    output = subprocess.run(['git', 'check-ignore', '--no-index', *names], cwd=ROOT, text=True, capture_output=True, check=True)
    assert set(output.stdout.splitlines()) == set(names)
    assert subprocess.run(['git', 'check-ignore', '.streamlit/secrets.toml.example'], cwd=ROOT, capture_output=True).returncode == 1
    assert subprocess.run(['git', 'ls-files', '.streamlit/secrets.toml', '.env', '.env.local'], cwd=ROOT, capture_output=True).stdout == b''
    assert 'ELEVENLABS_API_KEY = "paste-your-key-here"' in (ROOT / '.streamlit/secrets.toml.example').read_text()
