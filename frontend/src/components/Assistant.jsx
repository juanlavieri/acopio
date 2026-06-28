import { useEffect, useRef, useState } from "react";
import { Mic, Send, Square, Sparkles, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { useT } from "../lib/i18n.jsx";
import { useScope } from "../lib/scope.jsx";

export default function Assistant() {
  const { t } = useT();
  const { actionCenter } = useScope();
  const [messages, setMessages] = useState([{ role: "assistant", content: t("ai.greeting") }]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const scrollRef = useRef();
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const recognitionRef = useRef(null);

  useEffect(() => {
    api.get("/api/agent/status").then((s) => setAiEnabled(s.ai_enabled)).catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const send = async (text) => {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setInput("");
    const history = messages.filter((m) => m.role === "user" || m.role === "assistant");
    const next = [...messages, { role: "user", content: message }];
    setMessages(next);
    setBusy(true);
    try {
      const res = await api.post("/api/agent/chat", { message, history, center_id: actionCenter || null });
      setMessages([...next, { role: "assistant", content: res.reply, actions: res.actions }]);
      if (res.actions?.some((a) => ["record_stock", "create_item", "add_field", "create_table", "add_record"].includes(a.tool))) {
        window.dispatchEvent(new CustomEvent("acopio:data-changed"));
      }
    } catch (e) {
      setMessages([...next, { role: "assistant", content: `⚠️ ${e.message}` }]);
    } finally {
      setBusy(false);
    }
  };

  const startRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") return startBrowserSpeech();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setTranscribing(true);
        try {
          const fd = new FormData();
          fd.append("audio", blob, "audio.webm");
          const { text } = await api.upload("/api/voice/transcribe", fd);
          if (text) await send(text);
        } catch {
          startBrowserSpeech();
        } finally {
          setTranscribing(false);
        }
      };
      recorderRef.current = mr;
      mr.start();
      setRecording(true);
    } catch {
      startBrowserSpeech();
    }
  };

  const stopRecording = () => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    setRecording(false);
  };

  const startBrowserSpeech = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      setMessages((m) => [...m, { role: "assistant", content: t("ai.noVoice") }]);
      return;
    }
    const rec = new SR();
    rec.lang = navigator.language || "es-ES";
    rec.interimResults = false;
    rec.onresult = (e) => send(e.results[0][0].transcript);
    rec.onend = () => setRecording(false);
    rec.onerror = () => setRecording(false);
    recognitionRef.current = rec;
    rec.start();
    setRecording(true);
  };

  const toggleMic = () => {
    if (recording) {
      stopRecording();
      recognitionRef.current?.stop?.();
    } else {
      startRecording();
    }
  };

  const suggestions = [t("ai.s1"), t("ai.s2"), t("ai.s3"), t("ai.s4")];

  return (
    <div className="flex h-full flex-col">
      {!aiEnabled && <div className="bg-amber-50 px-4 py-2 text-xs text-amber-700">{t("ai.limited")}</div>}

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
              m.role === "user" ? "bg-brand-700 text-white" : "bg-slate-100 text-slate-800"}`}>
              <div className="whitespace-pre-wrap">{m.content}</div>
              {m.actions?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {m.actions.map((a, j) => (
                    <span key={j} className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-medium text-brand-700">
                      ⚡ {a.tool}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {(busy || transcribing) && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Loader2 size={16} className="animate-spin" /> {transcribing ? t("ai.transcribing") : t("ai.thinking")}
          </div>
        )}
        {messages.length <= 1 && (
          <div className="space-y-2 pt-2">
            {suggestions.map((s) => (
              <button key={s} onClick={() => send(s)}
                className="block w-full rounded-xl border border-slate-200 px-3 py-2 text-left text-xs text-slate-600 hover:border-brand-400 hover:bg-brand-50">
                <Sparkles size={12} className="mr-1 inline text-brand-500" />{s}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-slate-200 p-3">
        <div className="flex items-end gap-2">
          <button onClick={toggleMic}
            className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl transition ${
              recording ? "animate-pulse bg-red-500 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
            {recording ? <Square size={18} /> : <Mic size={18} />}
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            rows={1}
            placeholder={recording ? t("ai.listening") : t("ai.placeholder")}
            className="max-h-32 flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-brand-500"
          />
          <button onClick={() => send()} disabled={busy || !input.trim()}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-700 text-white hover:bg-brand-800 disabled:opacity-40">
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
