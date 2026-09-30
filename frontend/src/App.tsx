import { useEffect, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent, ReactNode } from 'react';
import { readEventStream, record } from './lib/stream.ts';
import { interruptTimeline, renderEvent, type TimelineItem } from './lib/timeline.ts';

const SUGGESTIONS = [
  'Qual o clima em São Paulo?',
  'Como está o tempo em Recife?',
  'Preciso de casaco em Curitiba?',
];

type IconName = 'arrow' | 'check' | 'cloud' | 'code' | 'compass' | 'sparkles' | 'stop' | 'tool';

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    arrow: <><path d="M5 12h13M13 6l6 6-6 6" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    cloud: <path d="M7 18h10a4 4 0 0 0 .4-8 6 6 0 0 0-11.5-1.6A4.8 4.8 0 0 0 7 18Z" />,
    code: <><path d="m8 9-3 3 3 3M16 9l3 3-3 3" /><path d="m14 6-4 12" /></>,
    compass: <><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" /></>,
    sparkles: <><path d="m12 3 1.3 3.7L17 8l-3.7 1.3L12 13l-1.3-3.7L7 8l3.7-1.3L12 3Z" /><path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3Z" /></>,
    stop: <rect x="7" y="7" width="10" height="10" rx="2" />,
    tool: <><path d="M14.5 6.5a4 4 0 0 1-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5l-2.4 2.4-3-3 2.4-2.4Z" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" width={size} height={size} fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function WeatherMark({ small = false }: { small?: boolean }) {
  return (
    <div className={small ? 'weather-mark weather-mark--small' : 'weather-mark'} aria-hidden="true">
      <span className="weather-mark__sun" />
      <span className="weather-mark__cloud"><Icon name="cloud" size={small ? 22 : 48} /></span>
      {!small && <><i className="rain rain--one" /><i className="rain rain--two" /><i className="rain rain--three" /></>}
    </div>
  );
}

function MessageContent({ content }: { content: string }) {
  return <p className="message-copy">{content.split(/(\*\*.*?\*\*)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={index}>{part.slice(2, -2)}</strong> : part,
  )}</p>;
}

function JSONBlock({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

function ToolCallCard({ item }: { item: Extract<TimelineItem, { kind: 'tool_call' }> }) {
  return (
    <article className="activity-card activity-card--request enter">
      <div className="activity-icon"><Icon name="code" size={17} /></div>
      <div className="activity-content">
        <span className="eyebrow">Chamada de ferramenta</span>
        <div className="activity-heading"><strong>{item.name}</strong><span className="status-pill">solicitada</span></div>
        <JSONBlock value={item.args} />
      </div>
    </article>
  );
}

function ToolProgressCard({ item }: { item: Extract<TimelineItem, { kind: 'tool' }> }) {
  const city = String(record(item.input).city ?? 'cidade informada');
  return (
    <article className={`activity-card activity-card--progress activity-card--${item.status} enter`}>
      <div className="activity-icon"><Icon name="tool" size={17} /></div>
      <div className="activity-content">
        <span className="eyebrow">Executando</span>
        <div className="activity-heading"><strong>{item.name}</strong></div>
        <p>Consultando as condições para {city}</p>
        {item.status === 'streaming' && <div className="progress-track"><span /></div>}
      </div>
      {item.status === 'complete' && <span className="complete-mark"><Icon name="check" size={14} /></span>}
    </article>
  );
}

function WeatherResultCard({ item }: { item: Extract<TimelineItem, { kind: 'tool_result' }> }) {
  const weather = record(item.output);
  return (
    <article className="weather-result enter">
      <div className="weather-result__top">
        <div><span className="eyebrow">Resultado da ferramenta</span><h3>{String(weather.city ?? 'Clima encontrado')}</h3></div>
        <WeatherMark small />
      </div>
      <div className="weather-result__reading">
        <strong>{String(weather.temp_c ?? '—')}<sup>°C</sup></strong>
        <span>{String(weather.condition ?? 'Condição indisponível')}</span>
      </div>
      <details><summary>Ver JSON recebido</summary><JSONBlock value={item.output} /></details>
    </article>
  );
}

function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <div className="timeline" aria-live="polite">
      {items.map((item) => {
        if (item.kind === 'model') {
          if (!item.content && item.status === 'complete') return null;
          return (
            <article className="assistant-row enter" key={item.id}>
              <div className="assistant-avatar"><Icon name="sparkles" size={17} /></div>
              <div className="assistant-message">
                <span className="message-author">RentalOps</span>
                {item.content ? <MessageContent content={item.content} /> :
                  <div className="typing" aria-label="RentalOps está pensando"><i /><i /><i /></div>}
                {item.status === 'streaming' && item.content && <span className="cursor" />}
                {item.status === 'interrupted' && <small>Resposta interrompida</small>}
              </div>
            </article>
          );
        }
        if (item.kind === 'tool_call') return <ToolCallCard item={item} key={item.id} />;
        if (item.kind === 'tool') return <ToolProgressCard item={item} key={item.id} />;
        return <WeatherResultCard item={item} key={item.id} />;
      })}
    </div>
  );
}

function App() {
  const [message, setMessage] = useState('');
  const [question, setQuestion] = useState('');
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const conversationEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => { conversationEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [timeline, question]);
  useEffect(() => () => controller.current?.abort(), []);

  function resizeComposer() {
    const element = textarea.current;
    if (!element) return;
    element.style.height = '0px';
    element.style.height = `${Math.min(element.scrollHeight, 132)}px`;
  }

  async function sendMessage(text = message) {
    const prompt = text.trim();
    if (!prompt || loading) return;
    const requestController = new AbortController();
    controller.current = requestController;
    setQuestion(prompt);
    setMessage('');
    setTimeline([]);
    setError('');
    setLoading(true);
    if (textarea.current) textarea.current.style.height = 'auto';

    try {
      const response = await fetch('/agent/execute', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ message: prompt }), signal: requestController.signal,
      });
      if (!response.ok) throw new Error(`A API respondeu com status ${response.status}.`);
      if (!response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('A API não retornou um fluxo SSE.');
      if (!response.body) throw new Error('O navegador não disponibilizou o fluxo da resposta.');
      await readEventStream(response.body, (event) => setTimeline((current) => renderEvent(current, event)));
    } catch (caught) {
      setTimeline((current) => interruptTimeline(current));
      if (!requestController.signal.aborted) setError(caught instanceof Error ? caught.message : 'Não foi possível concluir a resposta.');
    } finally {
      if (controller.current === requestController) controller.current = null;
      setLoading(false);
    }
  }

  function submit(event: FormEvent) { event.preventDefault(); void sendMessage(); }
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage(); }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RentalOps Agent, início"><WeatherMark small /><span><strong>RentalOps</strong><small>AI agent</small></span></a>
        <div className="stream-status"><i /><span>Streaming SSE</span></div>
      </header>

      <main className="workspace" id="top">
        <aside className="intro-panel">
          <div className="intro-badge"><Icon name="sparkles" size={15} /> Seu clima, em tempo real</div>
          <h1>Previsão simples.<br /><em>Conversa natural.</em></h1>
          <p>Eu consulto as condições da cidade e mostro cada etapa da resposta enquanto ela acontece.</p>
          <div className="feature-list">
            <div><span><Icon name="compass" size={18} /></span><p><strong>Qualquer cidade</strong><small>Pergunte do seu jeito</small></p></div>
            <div><span><Icon name="code" size={18} /></span><p><strong>Processo transparente</strong><small>Acompanhe a tool em ação</small></p></div>
          </div>
          <div className="ambient-weather" aria-hidden="true"><div className="orbit orbit--one" /><div className="orbit orbit--two" /><WeatherMark /></div>
        </aside>

        <section className="chat-card" aria-label="Conversa com o RentalOps Agent">
          <div className="chat-card__header">
            <div><span className="assistant-avatar assistant-avatar--header"><Icon name="sparkles" size={18} /></span></div>
            <div><h2>Assistente de clima</h2><p><span /> Online e pronto para ajudar</p></div>
            {question && !loading && <button className="new-chat" onClick={() => { setQuestion(''); setTimeline([]); setError(''); }}>Nova conversa</button>}
          </div>

          <div className="conversation">
            {!question ? (
              <div className="welcome enter">
                <div className="welcome-icon"><Icon name="cloud" size={30} /></div><span>Olá, eu sou o RentalOps Agent</span>
                <h2>Como está o tempo<br />por aí?</h2><p>Escolha uma sugestão ou pergunte sobre outra cidade.</p>
                <div className="suggestions">{SUGGESTIONS.map((suggestion) => (
                  <button key={suggestion} onClick={() => void sendMessage(suggestion)}><Icon name="compass" size={16} /><span>{suggestion}</span><Icon name="arrow" size={16} /></button>
                ))}</div>
              </div>
            ) : <><article className="user-row enter"><div className="user-message">{question}</div><span>Você</span></article><Timeline items={timeline} />
              {error && <div className="error-message" role="alert"><strong>Algo não saiu como esperado.</strong><span>{error}</span><button onClick={() => void sendMessage(question)}>Tentar novamente</button></div>}</>}
            <div ref={conversationEnd} />
          </div>

          <form className="composer" onSubmit={submit}>
            <div className="composer-box">
              <textarea ref={textarea} rows={1} value={message} maxLength={500} onChange={(event) => { setMessage(event.target.value); resizeComposer(); }}
                onKeyDown={handleKeyDown} placeholder="Pergunte sobre o clima de uma cidade..." aria-label="Mensagem" disabled={loading} />
              {loading ? <button className="send-button send-button--stop" type="button" onClick={() => controller.current?.abort()} aria-label="Interromper resposta"><Icon name="stop" size={18} /></button>
                : <button className="send-button" type="submit" disabled={!message.trim()} aria-label="Enviar mensagem"><Icon name="arrow" size={19} /></button>}
            </div>
            <p>Enter para enviar <span>·</span> Shift + Enter para quebrar linha</p>
          </form>
        </section>
      </main>
      <footer>Construído com <strong>LangGraph</strong> + <strong>FastAPI</strong></footer>
    </div>
  );
}

export default App;
