import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { AuthContext } from './authContext';

type Identity = {
  user_id: string;
  session_id: string;
  expires_at: string;
  idle_expires_at: string;
};

class ApiError extends Error {
  status: number;
  constructor(status: number) {
    super('Authentication request failed');
    this.status = status;
  }
}

async function request(path: string, body?: object): Promise<Identity | null> {
  const response = await fetch(`/api/auth/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers:
      body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError(response.status);
  if (response.status === 204) return null;
  return (await response.json()) as Identity;
}

function message(error: unknown, setting: boolean) {
  if (error instanceof ApiError) {
    if (error.status === 400 && setting)
      return 'Link inválido, expirado ou já utilizado. Procure o administrador para receber outro.';
    if (error.status === 401)
      return 'E-mail ou senha inválidos. Confira os dados e tente novamente.';
    if (error.status === 429)
      return 'Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.';
    if (error.status === 422)
      return 'Confira o e-mail e use uma senha de 12 a 128 caracteres.';
    if (error.status === 403)
      return 'Reabra o sistema pelo endereço oficial informado pelo administrador.';
  }
  return 'Não foi possível conectar ao sistema. Tente novamente em instantes.';
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [checking, setChecking] = useState(true);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [token, setToken] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    return window.location.pathname === '/definir-senha'
      ? params.get('token')
      : null;
  });
  const title = useRef<HTMLHeadingElement>(null);
  const lastActivity = useRef(0);
  const liveIdentity = useRef(identity);
  const generation = useRef(0);
  useEffect(() => {
    liveIdentity.current = identity;
  }, [identity]);

  const ended = useCallback(() => {
    generation.current += 1;
    setIdentity(null);
    setNotice(
      'Sua sessão terminou. Entre novamente para continuar. Seu trabalho nesta tela foi preservado.',
    );
  }, []);

  const checkSession = useCallback(async () => {
    const version = generation.current;
    try {
      const next = await request('session');
      if (version !== generation.current) return;
      setIdentity(next);
      setError('');
    } catch (failure) {
      if (version !== generation.current) return;
      if (failure instanceof ApiError && failure.status === 401) {
        setError('');
        if (liveIdentity.current) ended();
        else setIdentity(null);
      } else setError(message(failure, false));
    } finally {
      setChecking(false);
    }
  }, [ended]);

  useEffect(() => {
    // Remove fragment immediately; it is never sent in a URL or stored persistently.
    if (window.location.hash)
      window.history.replaceState(null, '', window.location.pathname);
    queueMicrotask(() => void checkSession());
    const interval = window.setInterval(() => void checkSession(), 30_000);
    return () => window.clearInterval(interval);
  }, [checkSession]);

  useEffect(() => {
    window.addEventListener('rentalops-session-ended', ended);
    return () => window.removeEventListener('rentalops-session-ended', ended);
  }, [ended]);

  useEffect(() => {
    if (!checking && (!identity || token)) title.current?.focus();
  }, [checking, identity, token]);

  useEffect(() => {
    if (!identity) return;
    const expiry = Math.min(
      Date.parse(identity.expires_at),
      Date.parse(identity.idle_expires_at),
    );
    const timeout = window.setTimeout(ended, Math.max(0, expiry - Date.now()));
    const activity = (event: Event) => {
      if (
        !event.isTrusted ||
        document.visibilityState !== 'visible' ||
        Date.now() - lastActivity.current < 30_000
      )
        return;
      lastActivity.current = Date.now();
      const version = generation.current;
      void request('activity', {})
        .then((next) => {
          if (version === generation.current) setIdentity(next);
        })
        .catch((failure: unknown) => {
          if (version !== generation.current) return;
          if (failure instanceof ApiError && failure.status === 401) ended();
          else setError(message(failure, false));
        });
    };
    window.addEventListener('pointerdown', activity);
    window.addEventListener('keydown', activity);
    return () => {
      window.clearTimeout(timeout);
      window.removeEventListener('pointerdown', activity);
      window.removeEventListener('keydown', activity);
    };
  }, [identity, ended]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (token && password !== confirmation) {
      setError('As senhas não coincidem. Confira a confirmação.');
      return;
    }
    setBusy(true);
    generation.current += 1;
    try {
      if (token) {
        await request('password/set', { token, password });
        setToken(null);
        setIdentity(null);
        setNotice('Senha definida. Entre com seu e-mail e a nova senha.');
        window.history.replaceState(null, '', '/');
        window.dispatchEvent(new PopStateEvent('popstate'));
      } else {
        setIdentity(await request('password/login', { email, password }));
        setNotice('');
      }
      setPassword('');
      setConfirmation('');
    } catch (failure) {
      setError(message(failure, Boolean(token)));
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    generation.current += 1;
    setBusy(true);
    setError('');
    try {
      await request('logout', {});
      setIdentity(null);
      setNotice('Você saiu. Entre novamente quando quiser continuar.');
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) ended();
      else
        setError(
          'Não foi possível sair. Tente novamente; sua sessão pode continuar ativa.',
        );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* Keep mounted drafts in memory when access expires. Hidden content is inert. */}
      <div
        hidden={!identity || Boolean(token) || checking}
        inert={!identity || Boolean(token) || checking}
      >
        <AuthContext.Provider
          value={{
            logout: () => void logout(),
            busy,
            authenticated: Boolean(identity) && !checking && !token,
          }}
        >
          {children}
        </AuthContext.Provider>
        {error && (
          <p className="auth-feedback" role="alert">
            {error}
          </p>
        )}
      </div>
      {(!identity || token || checking) && (
        <div className="auth-layout">
          <a className="skip-link" href="#auth-content">
            Pular para o conteúdo
          </a>
          <main className="auth-card" id="auth-content">
            <p className="section-kicker">RENTALOPS · ACESSO DA EQUIPE</p>
            <h1 ref={title} tabIndex={-1}>
              {checking
                ? 'Verificando acesso…'
                : token
                  ? 'Definir sua senha'
                  : 'Entrar no RentalOps'}
            </h1>
            {notice && (
              <p className="auth-feedback" role="status">
                {notice}
              </p>
            )}
            {error && (
              <p className="auth-feedback auth-feedback--error" role="alert">
                {error}
              </p>
            )}
            {checking ? (
              <p role="status">Aguarde um instante.</p>
            ) : (
              <>
                <p>
                  {token
                    ? 'Escolha uma senha pessoal. O link vale por 30 minutos e funciona uma única vez.'
                    : 'Use a conta individual autorizada pelo administrador.'}
                </p>
                <form onSubmit={(event) => void submit(event)} aria-busy={busy}>
                  {!token && (
                    <label htmlFor="login-email">
                      E-mail
                      <input
                        id="login-email"
                        type="email"
                        autoComplete="username"
                        required
                        maxLength={320}
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                      />
                    </label>
                  )}
                  <label htmlFor="login-password">
                    {token ? 'Nova senha' : 'Senha'}
                    <input
                      id="login-password"
                      type="password"
                      autoComplete={token ? 'new-password' : 'current-password'}
                      required
                      minLength={12}
                      maxLength={128}
                      aria-describedby="password-help"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </label>
                  <p id="password-help" className="auth-help">
                    De 12 a 128 caracteres. Você pode usar uma frase.
                  </p>
                  {token && (
                    <label htmlFor="password-confirmation">
                      Confirmar senha
                      <input
                        id="password-confirmation"
                        type="password"
                        autoComplete="new-password"
                        required
                        minLength={12}
                        maxLength={128}
                        value={confirmation}
                        onChange={(event) =>
                          setConfirmation(event.target.value)
                        }
                      />
                    </label>
                  )}
                  <button className="auth-button" type="submit" disabled={busy}>
                    {busy ? 'Aguarde…' : token ? 'Salvar senha' : 'Entrar'}
                  </button>
                </form>
                {error && (
                  <button
                    className="auth-retry"
                    type="button"
                    disabled={busy}
                    onClick={() => void checkSession()}
                  >
                    Verificar conexão novamente
                  </button>
                )}
                <p className="auth-help">
                  Primeiro acesso ou esqueceu a senha? Procure o administrador
                  para receber um link privado.
                </p>
              </>
            )}
          </main>
        </div>
      )}
    </>
  );
}
