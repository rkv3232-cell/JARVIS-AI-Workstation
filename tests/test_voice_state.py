import pytest
import asyncio
from backend.voice_service import voice_state_machine, VoiceState, list_audio_devices

@pytest.mark.asyncio
async def test_voice_state_transitions():
    await voice_state_machine.transition_to(VoiceState.IDLE)
    assert voice_state_machine.current_state == VoiceState.IDLE

    await voice_state_machine.transition_to(VoiceState.LISTENING)
    assert voice_state_machine.current_state == VoiceState.LISTENING

    await voice_state_machine.transition_to(VoiceState.THINKING)
    assert voice_state_machine.current_state == VoiceState.THINKING

    await voice_state_machine.transition_to(VoiceState.SPEAKING)
    assert voice_state_machine.current_state == VoiceState.SPEAKING

@pytest.mark.asyncio
async def test_audio_interruption_protocol():
    # Put machine into SPEAKING
    await voice_state_machine.transition_to(VoiceState.SPEAKING)
    assert voice_state_machine.current_state == VoiceState.SPEAKING

    # Call interrupt
    res = await voice_state_machine.interrupt()
    assert res["success"] is True
    assert res["was_speaking"] is True
    assert voice_state_machine.current_state == VoiceState.INTERRUPTED

    # Check that it resets back to LISTENING after delay
    await asyncio.sleep(0.35)
    assert voice_state_machine.current_state == VoiceState.LISTENING

def test_audio_devices_enumeration():
    devs = list_audio_devices()
    assert devs["success"] is True
    assert isinstance(devs["inputs"], list)
    assert isinstance(devs["outputs"], list)
