type WebkitAudioWindow = Window & typeof globalThis & {
  webkitAudioContext?: typeof AudioContext;
};

export function createAudioContext(): AudioContext | null {
  const AudioContextConstructor = window.AudioContext
    ?? (window as WebkitAudioWindow).webkitAudioContext;

  return AudioContextConstructor ? new AudioContextConstructor() : null;
}
