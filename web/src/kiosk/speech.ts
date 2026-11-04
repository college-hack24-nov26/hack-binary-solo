import { useEffect, useState } from "react";
import { LANG_TAG, type Lang } from "../i18n/i18n";

/**
 * Read-aloud with the browser's speechSynthesis, only with a voice that runs on this device (voice.localService) for the
 * patient's language. No local voice: no button. Never uses speech recognition (in Chrome it sends audio to a server).
 */
export function useLocalVoice(lang: Lang): SpeechSynthesisVoice | null {
  const [voice, setVoice] = useState<SpeechSynthesisVoice | null>(null);
  useEffect(() => {
    const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
    if (!synth) return;
    const pick = () => {
      const tag = LANG_TAG[lang].toLowerCase();
      const base = tag.slice(0, 2);
      const voices = synth.getVoices().filter((v) => v.localService);
      setVoice(voices.find((v) => v.lang.toLowerCase().replace("_", "-") === tag) ?? voices.find((v) => v.lang.toLowerCase().startsWith(base)) ?? null);
    };
    pick();
    synth.addEventListener?.("voiceschanged", pick);
    return () => synth.removeEventListener?.("voiceschanged", pick);
  }, [lang]);
  return voice;
}

export function speak(voice: SpeechSynthesisVoice | null, text: string) {
  const synth = window.speechSynthesis;
  if (!voice || !synth || !voice.localService) return;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.voice = voice;
  u.lang = voice.lang;
  u.rate = 0.9;
  synth.speak(u);
}

export function stopSpeaking() {
  window.speechSynthesis?.cancel();
}
