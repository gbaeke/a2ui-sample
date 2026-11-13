import {type FormEvent, useEffect, useRef, useState} from 'react';

import {A2uiSurface, type ReactCatalogComponent} from '@a2ui/react';
import type {SurfaceModel} from '@a2ui/web_core/v1_0';

import {Session, type SessionEvent} from './session';

const SUGGESTIONS = ['Show my week', 'Log 2 hours on Friday for Contoso', 'Show project budgets'];

interface ChatLine {
  from: 'user' | 'agent';
  text: string;
}

interface LogEntry {
  direction: 'in' | 'out' | 'error';
  payload: unknown;
}

const LOG_LABEL = {in: 'agent → renderer', out: 'renderer → agent', error: 'error'};

function useSurfaces(session: Session): SurfaceModel<ReactCatalogComponent>[] {
  const {processor} = session;
  const [surfaces, setSurfaces] = useState<SurfaceModel<ReactCatalogComponent>[]>([]);

  useEffect(() => {
    const sync = () => setSurfaces(Array.from(processor.getSurfaces().values()));
    const created = processor.onSurfaceCreated(sync);
    const deleted = processor.onSurfaceDeleted(sync);
    sync();
    return () => {
      created.unsubscribe();
      deleted.unsubscribe();
    };
  }, [processor]);

  return surfaces;
}

export function App() {
  const [session] = useState(() => new Session());
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState('');
  const surfaces = useSurfaces(session);
  const chatEnd = useRef<HTMLDivElement>(null);

  // Keep the newest chat line in view.
  useEffect(() => {
    chatEnd.current?.scrollIntoView({block: 'nearest'});
  }, [chat]);

  useEffect(() => {
    // Agent text arrives in streamed pieces: join the pieces of one reply
    // into one bubble. A reply starts with each request, typed or clicked.
    let replyStarted = false;
    const say = (line: ChatLine) => {
      const append = line.from === 'agent' && replyStarted;
      replyStarted = line.from === 'agent';
      setChat(prev => {
        const last = prev.at(-1);
        return append && last?.from === 'agent'
          ? [...prev.slice(0, -1), {from: 'agent', text: last.text + line.text}]
          : [...prev, line];
      });
    };
    const record = (entry: LogEntry) => setLog(prev => [entry, ...prev]);

    session.onEvent((event: SessionEvent) => {
      switch (event.kind) {
        case 'user-text':
          return say({from: 'user', text: event.text});
        case 'agent-text':
          return say({from: 'agent', text: event.text});
        case 'sent':
          replyStarted = false;
          return record({direction: 'out', payload: event.payload});
        case 'received':
          return record({direction: 'in', payload: event.payload});
        case 'error':
          return record({direction: 'error', payload: event.payload});
        case 'busy':
          return setBusy(event.busy);
      }
    });
  }, [session]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setDraft('');
    void session.sendText(text);
  }

  return (
    <main className="app">
      <header className="app__header">
        <h1>Project Hours</h1>
        <p>A2UI 1.0 over A2A. The agent answers with surfaces built from a declared catalog.</p>
      </header>

      <div className="app__body">
        <div className="app__main">
          <section className="panel chat">
            <div className="chat__lines">
              {chat.length === 0 ? (
                <p className="hours-muted">Ask the agent something, or pick a suggestion.</p>
              ) : (
                chat
                  .filter(line => line.text.trim())
                  .map((line, i) => (
                    <p key={i} className={`chat__line chat__line--${line.from}`}>
                      {line.text.trim()}
                    </p>
                  ))
              )}
              <div ref={chatEnd} />
            </div>
            <div className="chat__suggestions">
              {SUGGESTIONS.map(text => (
                <button
                  key={text}
                  type="button"
                  disabled={busy}
                  onClick={() => void session.sendText(text)}
                >
                  {text}
                </button>
              ))}
            </div>
            <form className="chat__form" onSubmit={submit}>
              <input
                value={draft}
                onChange={e => setDraft(e.target.value)}
                placeholder="Message the agent"
                aria-label="Message the agent"
              />
              <button type="submit" disabled={busy || !draft.trim()}>
                {busy ? 'Waiting…' : 'Send'}
              </button>
            </form>
          </section>

          {surfaces.map(surface => (
            <section key={surface.id} className="panel">
              <A2uiSurface surface={surface} />
            </section>
          ))}
        </div>

        <aside className="panel app__log">
          <h2>Wire log</h2>
          {log.length === 0 ? <p className="hours-muted">Nothing sent or received yet.</p> : null}
          {log.map((entry, i) => (
            <details key={log.length - i} open={i === 0}>
              <summary className={`log log--${entry.direction}`}>{LOG_LABEL[entry.direction]}</summary>
              <pre>{JSON.stringify(entry.payload, null, 2)}</pre>
            </details>
          ))}
        </aside>
      </div>
    </main>
  );
}
