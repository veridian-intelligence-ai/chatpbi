import { useEffect, useRef, useState, useCallback } from "react";
import { X, Mic, Volume2, Loader2 } from "lucide-react";
import { createRealtimeSession, fetchTTS, fetchVoiceConfig, transcribeAudio } from "@/lib/api";
import { useLanguage } from "@/i18n/LanguageContext";
import type { ModuleConfig } from "@/lib/modules";
import { useModelInfo } from "@/hooks/useModelInfo";
import {
  realtimeSupported,
  startRealtimeVoice,
  type RealtimeConnection,
  type RealtimeVoiceState,
} from "@/lib/realtimeVoice";

type VoiceState = "idle" | "listening" | "processing" | "speaking" | "unsupported";

/** realtime: voz ao vivo da OpenAI (WebRTC); classic: gravação + ElevenLabs. */
type VoiceEngine = "realtime" | "classic";

function voiceStateFromRealtime(state: RealtimeVoiceState): VoiceState {
  if (state === "listening") return "listening";
  if (state === "speaking") return "speaking";
  if (state === "closed") return "idle";
  return "processing"; // connecting | thinking
}

interface VoiceModeProps {
  open: boolean;
  onClose: () => void;
  module: ModuleConfig;
  onSendVoice: (text: string) => Promise<string | null>;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  baseR: number;
  r: number;
  alpha: number;
  angle: number;
  dist: number;
}

function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4;codecs=mp4a.40.2", "audio/mp4", "audio/aac"];
  for (const c of candidates) {
    try {
      if (MediaRecorder.isTypeSupported(c)) return c;
    } catch {
      /* noop */
    }
  }
  return "";
}

function contentTypeFor(mime: string): string {
  if (!mime) return "application/octet-stream";
  if (mime.startsWith("audio/webm")) return "audio/webm";
  if (mime.startsWith("audio/mp4")) return "audio/mp4";
  if (mime.startsWith("audio/aac")) return "audio/aac";
  return mime.split(";")[0];
}

const SILENCE_THRESHOLD = 0.08;
const SILENCE_DURATION_MS = 800;
const MIN_RECORDING_MS = 1000;
const MAX_RECORDING_MS = 12000;

let audioUnlocked = false;

async function unlockAudioOnIOS(audio: HTMLAudioElement): Promise<void> {
  if (audioUnlocked) return;
  try {
    const AudioCtor: typeof AudioContext =
      (window as unknown as { AudioContext: typeof AudioContext }).AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (AudioCtor) {
      const ctx = new AudioCtor();
      if (ctx.state === "suspended") await ctx.resume();
      const buf = ctx.createBuffer(1, 1, 22050);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(0);
      await ctx.close();
    }
    const silence = new Blob(
      [new Uint8Array([255, 227, 24, 196, 0, 0, 0, 3, 72, 1, 64, 0, 0, 4, 132, 16, 31, 227, 192, 0, 0, 0, 0])],
      { type: "audio/mpeg" },
    );
    const url = URL.createObjectURL(silence);
    audio.src = url;
    audio.volume = 0;
    try {
      await audio.play();
      audio.pause();
    } catch {
      // Best-effort audio unlock: play() may reject (e.g. autoplay policy); ignore safely.
    }
    audio.volume = 1;
    audio.removeAttribute("src");
    URL.revokeObjectURL(url);
    audioUnlocked = true;
  } catch {
    // Audio unlock is best-effort; if AudioContext/playback is unavailable, ignore safely.
  }
}

export function VoiceMode({ open, onClose, module, onSendVoice }: VoiceModeProps) {
  const { language, t } = useLanguage();
  const isPt = language.toLowerCase().startsWith("pt");
  const modelInfo = useModelInfo();

  const [state, setState] = useState<VoiceState>("idle");
  const [engine, setEngine] = useState<VoiceEngine | null>(null);
  const [realtimeDetail, setRealtimeDetail] = useState<RealtimeVoiceState | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const realtimeRef = useRef<RealtimeConnection | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const audioRef = useRef<HTMLAudioElement>(null);
  const ttsUrlRef = useRef<string | null>(null);

  // Recording
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recCtxRef = useRef<AudioContext | null>(null);
  const recAnalyserRef = useRef<AnalyserNode | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeTypeRef = useRef<string>("");
  const silenceStartRef = useRef<number | null>(null);
  const recordStartRef = useRef<number>(0);
  const silenceCheckRef = useRef<number | null>(null);

  const audioLevelRef = useRef<number>(0);
  const stateRef = useRef<VoiceState>("idle");
  stateRef.current = state;
  const sessionActiveRef = useRef<boolean>(false);
  const startListeningRef = useRef<(() => void) | null>(null);

  const subject = modelInfo.subject || (isPt ? "os dados" : "the data");
  const labels = {
    moduleName: t(module.nameKey),
    live: isPt ? "ao vivo" : "live",
    idle: isPt ? "Toque para falar" : "Tap to speak",
    listening: isPt ? "Ouvindo..." : "Listening...",
    processing: isPt ? "Processando..." : "Processing...",
    speaking: isPt ? "Respondendo..." : "Responding...",
    realtimeListening: isPt ? "Pode falar" : "Go ahead",
    realtimeConnecting: isPt ? "Conectando..." : "Connecting...",
    realtimeThinking: isPt ? "Consultando os dados..." : "Checking the data...",
    realtimeError: isPt
      ? "Não foi possível ligar a voz ao vivo agora. Tente de novo."
      : "Could not start live voice right now. Please try again.",
    greeting: isPt
      ? `Cumprimente a pessoa em uma frase curta, em português do Brasil, e diga que ela pode perguntar sobre ${subject}.`
      : `Greet the person in one short sentence, in English, and say they can ask about ${subject}.`,
    unsupported: isPt
      ? "Seu dispositivo não suporta gravação de áudio."
      : "Your device does not support audio recording.",
    close: isPt ? "Fechar" : "Close",
    micLabel: isPt ? "Microfone" : "Microphone",
  };

  // Particle animation
  useEffect(() => {
    if (!open) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    const dpr = window.devicePixelRatio || 1;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const PARTICLE_COUNT = 110;
    const particles: Particle[] = [];
    const cwInit = canvas.width / dpr;
    const chInit = canvas.height / dpr;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const angle = Math.random() * Math.PI * 2;
      const dist = Math.random() * Math.min(cwInit, chInit) * 0.4;
      particles.push({
        x: cwInit / 2 + Math.cos(angle) * dist,
        y: chInit / 2 + Math.sin(angle) * dist,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        baseR: 1 + Math.random() * 2,
        r: 1 + Math.random() * 2,
        alpha: 0.2 + Math.random() * 0.4,
        angle,
        dist,
      });
    }

    let tick = 0;
    const draw = () => {
      const cw = canvas.width / dpr;
      const ch = canvas.height / dpr;
      const cx = cw / 2;
      const cy = ch / 2;
      ctx.clearRect(0, 0, cw, ch);
      tick += 1;

      const s = stateRef.current;

      let level = 0;
      const analyser = s === "listening" ? recAnalyserRef.current : null;
      if (analyser) {
        const arr = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(arr);
        let sum = 0;
        for (let i = 0; i < arr.length; i++) sum += arr[i];
        level = sum / arr.length / 255;
        audioLevelRef.current = audioLevelRef.current * 0.6 + level * 0.4;
      } else {
        if (s === "speaking") {
          audioLevelRef.current = 0.3 + Math.sin(tick * 0.08) * 0.15;
        } else {
          audioLevelRef.current *= 0.92;
        }
      }

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        if (s === "idle" || s === "unsupported") {
          p.x += p.vx * 0.4;
          p.y += p.vy * 0.4;
          const dx = p.x - cx;
          const dy = p.y - cy;
          const d = Math.hypot(dx, dy);
          const max = Math.min(cw, ch) * 0.42;
          if (d > max) {
            p.x -= dx * 0.02;
            p.y -= dy * 0.02;
          }
          p.r = p.baseR;
          p.alpha = 0.18 + Math.sin((tick + i * 5) * 0.02) * 0.05;
        } else if (s === "listening") {
          const lvl = audioLevelRef.current;
          const dx = p.x - cx;
          const dy = p.y - cy;
          const d = Math.hypot(dx, dy) || 0.001;
          const ux = dx / d;
          const uy = dy / d;
          const push = 0.3 + lvl * 6;
          p.x += ux * push + (Math.random() - 0.5) * 0.6;
          p.y += uy * push + (Math.random() - 0.5) * 0.6;
          const max = Math.min(cw, ch) * (0.32 + lvl * 0.25);
          if (d > max) {
            p.x = cx + ux * max * 0.7;
            p.y = cy + uy * max * 0.7;
          }
          p.r = p.baseR * (1.1 + lvl * 2);
          p.alpha = 0.55 + lvl * 0.4;
        } else if (s === "processing") {
          p.angle += 0.02 + (i % 7) * 0.001;
          p.dist += Math.sin((tick + i) * 0.05) * 0.4;
          const max = Math.min(cw, ch) * 0.35;
          if (p.dist > max) p.dist = max;
          if (p.dist < 20) p.dist = 20;
          p.x = cx + Math.cos(p.angle) * p.dist;
          p.y = cy + Math.sin(p.angle) * p.dist;
          p.r = p.baseR;
          p.alpha = 0.45;
        } else if (s === "speaking") {
          const lvl = audioLevelRef.current;
          const baseDist = Math.min(cw, ch) * 0.18;
          const waveSpeed = 0.04 + lvl * 0.12;
          const phase = (tick * waveSpeed + i * 0.18) % (Math.PI * 2);
          const ring = baseDist + (Math.sin(phase) * 0.5 + 0.5) * baseDist * (1 + lvl * 1.5);
          p.angle += 0.003;
          p.x = cx + Math.cos(p.angle + i * 0.4) * ring;
          p.y = cy + Math.sin(p.angle + i * 0.4) * ring;
          p.r = p.baseR * (1 + lvl * 1.2);
          p.alpha = 0.4 + lvl * 0.5;
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        // Signal #2FBF8F. Canvas 2D não resolve var(--…), por isso usa-se o RGB da marca.
        ctx.fillStyle = `rgba(47, 191, 143, ${Math.min(0.95, Math.max(0.05, p.alpha))})`;
        ctx.shadowColor = "rgba(47, 191, 143, 0.6)";
        ctx.shadowBlur = s === "idle" ? 4 : 10;
        ctx.fill();
      }
      ctx.shadowBlur = 0;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [open]);

  const cleanupTTS = useCallback(() => {
    const a = audioRef.current;
    if (a) {
      try {
        a.pause();
      } catch {
        /* noop */
      }
      try {
        a.removeAttribute("src");
        a.load();
      } catch {
        /* noop */
      }
    }
    if (ttsUrlRef.current) {
      try {
        URL.revokeObjectURL(ttsUrlRef.current);
      } catch {
        /* noop */
      }
      ttsUrlRef.current = null;
    }
  }, []);

  const cleanupRecording = useCallback(() => {
    if (silenceCheckRef.current !== null) {
      cancelAnimationFrame(silenceCheckRef.current);
      silenceCheckRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      try {
        recorderRef.current.stop();
      } catch {
        /* noop */
      }
    }
    recorderRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((tr) => tr.stop());
      streamRef.current = null;
    }
    if (recCtxRef.current) {
      try {
        recCtxRef.current.close();
      } catch {
        /* noop */
      }
      recCtxRef.current = null;
    }
    recAnalyserRef.current = null;
    silenceStartRef.current = null;
    chunksRef.current = [];
  }, []);

  const stopRealtime = useCallback(() => {
    const connection = realtimeRef.current;
    realtimeRef.current = null;
    connection?.close();
  }, []);

  useEffect(() => {
    if (!open) {
      sessionActiveRef.current = false;
      stopRealtime();
      cleanupRecording();
      cleanupTTS();
      setState("idle");
      setRealtimeDetail(null);
      setErrorText(null);
      setEngine(null);
      audioUnlocked = false;
      return;
    }
    let cancelled = false;
    fetchVoiceConfig()
      .then((config) => {
        if (cancelled) return;
        setEngine(config.realtime && realtimeSupported() ? "realtime" : "classic");
      })
      .catch(() => {
        if (!cancelled) setEngine("classic");
      });
    return () => {
      cancelled = true;
    };
  }, [open, cleanupRecording, cleanupTTS, stopRealtime]);

  useEffect(() => {
    if (!open || engine === null) return;
    const supported =
      engine === "realtime"
        ? realtimeSupported()
        : typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
    if (!supported) setState("unsupported");
  }, [open, engine]);

  /** Liga o nível do microfone à animação (estado "listening"). */
  const attachMicAnalyser = useCallback((stream: MediaStream) => {
    try {
      const AudioCtor: typeof AudioContext =
        (window as unknown as { AudioContext: typeof AudioContext }).AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const actx = new AudioCtor();
      if (actx.state === "suspended") actx.resume().catch(() => undefined);
      const source = actx.createMediaStreamSource(stream);
      const analyser = actx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      recCtxRef.current = actx;
      recAnalyserRef.current = analyser;
    } catch {
      /* animação sem nível do microfone */
    }
  }, []);

  const startRealtime = useCallback(async () => {
    setErrorText(null);
    setRealtimeDetail("connecting");
    setState("processing");
    const audio = audioRef.current;
    if (!audio) return;
    try {
      const session = await createRealtimeSession();
      if (!sessionActiveRef.current) return;
      audio.autoplay = true;
      const connection = await startRealtimeVoice({
        clientSecret: session.client_secret,
        audioElement: audio,
        greeting: labels.greeting,
        handlers: {
          onState: (next) => {
            if (next === "closed") {
              realtimeRef.current = null;
              sessionActiveRef.current = false;
              cleanupRecording();
              setRealtimeDetail(null);
              setState("idle");
              return;
            }
            setRealtimeDetail(next);
            setState(voiceStateFromRealtime(next));
          },
          onToolCall: (question) => onSendVoice(question),
          onError: (message) => console.warn("[VoiceMode] realtime:", message),
        },
      });
      if (!sessionActiveRef.current) {
        connection.close();
        return;
      }
      realtimeRef.current = connection;
      attachMicAnalyser(connection.micStream);
    } catch (err) {
      console.warn("[VoiceMode] realtime start failed", err);
      realtimeRef.current = null;
      sessionActiveRef.current = false;
      setRealtimeDetail(null);
      setState("idle");
      setErrorText(labels.realtimeError);
    }
  }, [attachMicAnalyser, cleanupRecording, labels.greeting, labels.realtimeError, onSendVoice]);

  const playTTS = useCallback(
    async (text: string) => {
      const audio = audioRef.current;
      if (!audio) return;
      try {
        const blob = await fetchTTS(text);
        const url = URL.createObjectURL(blob);
        ttsUrlRef.current = url;

        audio.src = url;
        audio.load();
        setState("speaking");
        await audio.play();

        await new Promise<void>((resolve) => {
          const done = () => {
            audio.onended = null;
            audio.onerror = null;
            resolve();
          };
          audio.onended = done;
          audio.onerror = done;
        });
      } catch {
        /* silent */
      } finally {
        cleanupTTS();
        setState("idle");
        if (sessionActiveRef.current) {
          setTimeout(() => {
            if (sessionActiveRef.current && stateRef.current === "idle") {
              startListeningRef.current?.();
            }
          }, 250);
        }
      }
    },
    [cleanupTTS],
  );

  const handleTranscript = useCallback(
    async (text: string) => {
      const cleanText = text.trim();

      // Filtra transcrições que são só descrições de ruído (entre parênteses)
      // ou demasiado curtas para ser pergunta real
      const isOnlyNoiseDescription = /^\(.*\)$/.test(cleanText);
      const isTooShort = cleanText.length < 3;

      if (!cleanText || isOnlyNoiseDescription || isTooShort) {
        setState("idle");
        if (sessionActiveRef.current) {
          setTimeout(() => {
            if (sessionActiveRef.current && stateRef.current === "idle") startListeningRef.current?.();
          }, 250);
        }
        return;
      }
      setState("processing");
      const answer = await onSendVoice(cleanText);
      if (!answer) {
        setState("idle");
        if (sessionActiveRef.current) {
          setTimeout(() => {
            if (sessionActiveRef.current && stateRef.current === "idle") startListeningRef.current?.();
          }, 250);
        }
        return;
      }
      await playTTS(answer);
    },
    [onSendVoice, playTTS],
  );

  const stopRecording = useCallback(() => {
    if (silenceCheckRef.current !== null) {
      cancelAnimationFrame(silenceCheckRef.current);
      silenceCheckRef.current = null;
    }
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") {
      try {
        rec.stop();
      } catch {
        /* noop */
      }
    }
  }, []);

  const startListening = useCallback(async () => {
    if (stateRef.current !== "idle") return;
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setState("unsupported");
      return;
    }
    const mimeType = pickMimeType();
    mimeTypeRef.current = mimeType;

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      console.warn("[VoiceMode] getUserMedia failed", err);
      setState("idle");
      return;
    }
    streamRef.current = stream;

    let recorder: MediaRecorder;
    try {
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    } catch (err) {
      console.warn("[VoiceMode] MediaRecorder ctor failed, retrying default", err);
      try {
        recorder = new MediaRecorder(stream);
      } catch (err2) {
        console.warn("[VoiceMode] MediaRecorder unsupported", err2);
        cleanupRecording();
        setState("unsupported");
        return;
      }
    }
    if (recorder.mimeType) mimeTypeRef.current = recorder.mimeType;
    recorderRef.current = recorder;
    chunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      const localChunks = chunksRef.current.slice();
      const localStream = streamRef.current;
      const localCtx = recCtxRef.current;
      const localMime = mimeTypeRef.current;
      if (localStream) localStream.getTracks().forEach((tr) => tr.stop());
      if (localCtx) {
        try {
          localCtx.close();
        } catch {
          /* noop */
        }
      }
      streamRef.current = null;
      recCtxRef.current = null;
      recAnalyserRef.current = null;
      recorderRef.current = null;
      chunksRef.current = [];

      if (localChunks.length === 0) {
        setState("idle");
        // Volta a ouvir se sessão activa (era ruído, não fala real)
        if (sessionActiveRef.current) {
          setTimeout(() => {
            if (sessionActiveRef.current && stateRef.current === "idle") {
              startListeningRef.current?.();
            }
          }, 250);
        }
        return;
      }
      const blob = new Blob(localChunks, { type: localMime });
      if (blob.size < 1000) {
        // Áudio demasiado pequeno, provavelmente vazio
        setState("idle");
        if (sessionActiveRef.current) {
          setTimeout(() => {
            if (sessionActiveRef.current && stateRef.current === "idle") {
              startListeningRef.current?.();
            }
          }, 250);
        }
        return;
      }
      setState("processing");
      try {
        const text = await transcribeAudio(blob, contentTypeFor(localMime));
        await handleTranscript(text);
      } catch (err) {
        console.warn("[VoiceMode] transcribe failed", err);
        setState("idle");
        // Se sessão ainda activa, volta automaticamente a ouvir
        if (sessionActiveRef.current) {
          setTimeout(() => {
            if (sessionActiveRef.current && stateRef.current === "idle") {
              startListeningRef.current?.();
            }
          }, 250);
        }
      }
    };

    try {
      const AudioCtor: typeof AudioContext =
        (window as unknown as { AudioContext: typeof AudioContext }).AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const actx = new AudioCtor();
      if (actx.state === "suspended") {
        try {
          await actx.resume();
        } catch {
          /* noop */
        }
      }
      const source = actx.createMediaStreamSource(stream);
      const analyser = actx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      recCtxRef.current = actx;
      recAnalyserRef.current = analyser;
    } catch {
      /* noop */
    }

    recordStartRef.current = performance.now();
    silenceStartRef.current = null;
    setState("listening");
    try {
      recorder.start(250);
    } catch {
      cleanupRecording();
      setState("idle");
      return;
    }

    let voiceDurationMs = 0;
    const MIN_VOICE_DURATION_MS = 600;

    const loop = () => {
      if (!recorderRef.current || recorderRef.current.state === "inactive") return;
      const now = performance.now();
      if (now - recordStartRef.current > MAX_RECORDING_MS) {
        stopRecording();
        return;
      }
      const an = recAnalyserRef.current;
      if (an) {
        const arr = new Uint8Array(an.frequencyBinCount);
        an.getByteFrequencyData(arr);
        let sum = 0;
        for (let i = 0; i < arr.length; i++) sum += arr[i];
        const level = sum / arr.length / 255;
        if (level < SILENCE_THRESHOLD) {
          if (silenceStartRef.current === null) silenceStartRef.current = now;
          else if (
            now - silenceStartRef.current > SILENCE_DURATION_MS &&
            now - recordStartRef.current > MIN_RECORDING_MS
          ) {
            // Só envia se houve voz real (não só ruído)
            if (voiceDurationMs < MIN_VOICE_DURATION_MS) {
              // Áudio só com ruído — descarta e volta a ouvir
              chunksRef.current = [];
            }
            stopRecording();
            return;
          }
        } else {
          silenceStartRef.current = null;
          voiceDurationMs += 16; // aprox 60fps
        }
      }
      silenceCheckRef.current = requestAnimationFrame(loop);
    };
    silenceCheckRef.current = requestAnimationFrame(loop);
  }, [cleanupRecording, handleTranscript, stopRecording]);

  startListeningRef.current = startListening;

  const handleButtonTap = () => {
    if (engine === "realtime") {
      if (state === "idle" && !realtimeRef.current) {
        sessionActiveRef.current = true;
        const audio = audioRef.current;
        (audio ? unlockAudioOnIOS(audio) : Promise.resolve()).then(() => {
          if (sessionActiveRef.current) startRealtime();
        });
      } else {
        sessionActiveRef.current = false;
        stopRealtime();
        cleanupRecording();
        setRealtimeDetail(null);
        setState("idle");
      }
      return;
    }
    if (state === "idle") {
      sessionActiveRef.current = true;
      if (audioRef.current) {
        unlockAudioOnIOS(audioRef.current).then(() => {
          startListening();
        });
      } else {
        startListening();
      }
    } else {
      sessionActiveRef.current = false;
      if (state === "listening") stopRecording();
      else if (state === "speaking") {
        try {
          audioRef.current?.pause();
        } catch {
          /* noop */
        }
        cleanupTTS();
        setState("idle");
      }
    }
  };

  if (!open) return null;

  const isRealtime = engine === "realtime";
  const stateLabel =
    state === "listening"
      ? isRealtime
        ? labels.realtimeListening
        : labels.listening
      : state === "processing"
        ? isRealtime
          ? realtimeDetail === "thinking"
            ? labels.realtimeThinking
            : labels.realtimeConnecting
          : labels.processing
        : state === "speaking"
          ? labels.speaking
          : state === "idle"
            ? labels.idle
            : "";

  const buttonStyle: React.CSSProperties = {
    width: 72,
    height: 72,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#fff",
    transition: "background-color 200ms ease, box-shadow 200ms ease, transform 150ms ease",
    backgroundColor:
      state === "listening"
        ? "hsl(var(--destructive))"
        : state === "processing"
          ? "hsl(var(--muted-foreground))"
          : "hsl(var(--ring))",
    boxShadow:
      state === "listening"
        ? "0 0 0 8px hsl(var(--destructive) / 0.18), 0 8px 24px hsl(var(--destructive) / 0.45)"
        : state === "processing"
          ? "0 6px 18px rgba(0,0,0,0.4)"
          : "0 0 0 6px hsl(var(--ring) / 0.18), 0 8px 24px hsl(var(--ring) / 0.45)",
  };

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-50 flex flex-col animate-fade-in"
      style={{ background: "hsl(var(--background))" }}
    >
      <div className="flex items-center justify-between px-5 pt-5 pb-2 safe-area-top">
        <span className="text-[12px] tracking-wide uppercase text-muted-foreground">
          {labels.moduleName}
          {isRealtime ? ` · ${labels.live}` : ""}
        </span>
        <button
          onClick={onClose}
          aria-label={labels.close}
          className="w-9 h-9 rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="relative flex-1 w-full" style={{ minHeight: 0 }}>
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
      </div>

      <audio ref={audioRef} playsInline preload="none" className="hidden" />

      <div className="flex flex-col items-center justify-start px-6 pb-10 pt-4 gap-4 safe-area-bottom">
        <button
          onClick={handleButtonTap}
          disabled={
            state === "unsupported" || engine === null || (!isRealtime && state === "processing")
          }
          aria-label={labels.micLabel}
          className={`focus:outline-none active:scale-95 ${state === "listening" ? "animate-pulse" : ""}`}
          style={buttonStyle}
        >
          {state === "processing" ? (
            <Loader2 className="h-7 w-7 animate-spin" />
          ) : state === "speaking" ? (
            <Volume2 className="h-7 w-7" />
          ) : (
            <Mic className="h-7 w-7" />
          )}
        </button>
        {state === "unsupported" ? (
          <p className="text-[13px] text-destructive text-center max-w-md">{labels.unsupported}</p>
        ) : (
          <p className="text-[12px] tracking-wide text-muted-foreground uppercase min-h-[16px]">{stateLabel}</p>
        )}
        {errorText && state !== "unsupported" && (
          <p className="text-[13px] text-destructive text-center max-w-md">{errorText}</p>
        )}
      </div>
    </div>
  );
}
