import { useContext, useState } from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthGate } from './auth';
import { AuthContext } from './authContext';

const identity = () => ({
  user_id: 'synthetic',
  session_id: 'synthetic',
  expires_at: new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString(),
  idle_expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
});
const response = (status: number, data = identity()) => ({
  ok: status < 400,
  status,
  json: async () => data,
});
const fetchMock = vi.fn();

function Draft() {
  const [draft, setDraft] = useState('');
  return (
    <label>
      Rascunho
      <input value={draft} onChange={(event) => setDraft(event.target.value)} />
    </label>
  );
}
function ProtectedView() {
  const { logout, busy } = useContext(AuthContext);
  return (
    <>
      <h1>Operação</h1>
      <Draft />
      <button disabled={busy} onClick={logout}>
        Sair
      </button>
    </>
  );
}
function view() {
  return render(
    <AuthGate>
      <ProtectedView />
    </AuthGate>,
  );
}
beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(response(401));
  vi.stubGlobal('fetch', fetchMock);
  window.history.replaceState(null, '', '/');
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('closed team access', () => {
  it('explains password-setting budget without claiming success or access', async () => {
    window.history.replaceState(
      null,
      '',
      '/definir-senha#token=synthetic-token',
    );
    const user = userEvent.setup();
    view();
    await screen.findByLabelText('Nova senha');
    for (const label of ['Nova senha', 'Confirmar senha']) {
      await user.type(screen.getByLabelText(label), 'synthetic pass phrase');
    }
    fetchMock.mockResolvedValue(response(429));
    await user.click(screen.getByRole('button', { name: 'Salvar senha' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Aguarde 15 minutos',
    );
    expect(
      screen.getByRole('heading', { name: 'Definir sua senha' }),
    ).toBeVisible();
    expect(
      screen.queryByRole('heading', { name: 'Operação' }),
    ).not.toBeInTheDocument();
    expect(window.location.hash).toBe('');
  });
  it('ignores an old polling response after logout instead of restoring access', async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValueOnce(response(200));
    view();
    await act(async () => {});
    let resolve: (value: ReturnType<typeof response>) => void = () => {};
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    fetchMock.mockResolvedValueOnce(response(204));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Sair' }));
    });
    expect(screen.getByRole('status')).toHaveTextContent('Você saiu');
    await act(async () => resolve(response(200)));
    expect(
      screen.getByRole('heading', { name: 'Entrar no RentalOps' }),
    ).toBeVisible();
    expect(
      screen.queryByRole('heading', { name: 'Operação' }),
    ).not.toBeInTheDocument();
  });
  it('guards internal content, focuses login and has no signup or Google', async () => {
    view();
    const heading = await screen.findByRole('heading', {
      name: 'Entrar no RentalOps',
    });
    expect(heading).toHaveFocus();
    expect(
      screen.queryByRole('heading', { name: 'Operação' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Google/)).not.toBeInTheDocument();
    expect(screen.getByText(/Procure o administrador/)).toBeVisible();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/session',
      expect.objectContaining({ method: 'GET', credentials: 'same-origin' }),
    );
  });
  it.each([401, 403, 422, 429, 503])(
    'shows actionable failure %s without claiming access',
    async (status) => {
      const user = userEvent.setup();
      view();
      await screen.findByLabelText('E-mail');
      await user.type(
        screen.getByLabelText('E-mail'),
        'person@example.invalid',
      );
      await user.type(screen.getByLabelText('Senha'), 'synthetic pass phrase');
      fetchMock.mockResolvedValue(response(status));
      await user.click(screen.getByRole('button', { name: 'Entrar' }));
      expect(await screen.findByRole('alert')).toBeVisible();
      expect(
        screen.queryByRole('heading', { name: 'Operação' }),
      ).not.toBeInTheDocument();
    },
  );
  it('enters, preserves a mounted draft on logout, and re-enters', async () => {
    const user = userEvent.setup();
    view();
    await screen.findByLabelText('E-mail');
    await user.type(screen.getByLabelText('E-mail'), 'person@example.invalid');
    await user.type(screen.getByLabelText('Senha'), 'synthetic pass phrase');
    fetchMock.mockResolvedValue(response(200));
    await user.click(screen.getByRole('button', { name: 'Entrar' }));
    await screen.findByRole('heading', { name: 'Operação' });
    await user.type(
      screen.getByLabelText('Rascunho'),
      'preservar meu trabalho',
    );
    fetchMock.mockResolvedValue(response(204));
    await user.click(screen.getByRole('button', { name: 'Sair' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Você saiu');
    await user.type(screen.getByLabelText('Senha'), 'synthetic pass phrase');
    fetchMock.mockResolvedValue(response(200));
    await user.click(screen.getByRole('button', { name: 'Entrar' }));
    expect(await screen.findByLabelText('Rascunho')).toHaveValue(
      'preservar meu trabalho',
    );
  });
  it('reads and removes the fragment and sends token only in typed body', async () => {
    window.history.replaceState(
      null,
      '',
      '/definir-senha#token=synthetic-token',
    );
    const user = userEvent.setup();
    view();
    await screen.findByRole('heading', { name: 'Definir sua senha' });
    expect(window.location.hash).toBe('');
    await user.type(
      screen.getByLabelText('Nova senha'),
      'synthetic pass phrase',
    );
    await user.type(
      screen.getByLabelText('Confirmar senha'),
      'different pass phrase',
    );
    await user.click(screen.getByRole('button', { name: 'Salvar senha' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('não coincidem');
    await user.clear(screen.getByLabelText('Confirmar senha'));
    await user.type(
      screen.getByLabelText('Confirmar senha'),
      'synthetic pass phrase',
    );
    fetchMock.mockResolvedValue(response(204));
    await user.click(screen.getByRole('button', { name: 'Salvar senha' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Senha definida',
    );
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/auth/password/set',
      expect.objectContaining({
        body: JSON.stringify({
          token: 'synthetic-token',
          password: 'synthetic pass phrase',
        }),
      }),
    );
    expect(screen.getByLabelText('Senha')).toHaveValue('');
  });
  it('guides expired or reused links to administrator', async () => {
    window.history.replaceState(
      null,
      '',
      '/definir-senha#token=synthetic-token',
    );
    const user = userEvent.setup();
    view();
    await screen.findByLabelText('Nova senha');
    for (const label of ['Nova senha', 'Confirmar senha'])
      await user.type(screen.getByLabelText(label), 'synthetic pass phrase');
    fetchMock.mockResolvedValue(response(400));
    await user.click(screen.getByRole('button', { name: 'Salvar senha' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Procure o administrador',
    );
  });
  it('keeps access on failed logout and reports uncertainty', async () => {
    fetchMock.mockResolvedValue(response(200));
    const user = userEvent.setup();
    view();
    await screen.findByRole('button', { name: 'Sair' });
    fetchMock.mockRejectedValue(new Error('offline'));
    await user.click(screen.getByRole('button', { name: 'Sair' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'sessão pode continuar ativa',
    );
    expect(screen.getByRole('heading', { name: 'Operação' })).toBeVisible();
  });
  it('polling does not send activity and revocation preserves drafts', async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue(response(200));
    view();
    await act(async () => {});
    expect(screen.getByRole('heading', { name: 'Operação' })).toBeVisible();
    fetchMock.mockResolvedValue(response(401));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(screen.getByRole('status')).toHaveTextContent('sessão terminou');
    expect(
      fetchMock.mock.calls.every((call) => call[0] === '/api/auth/session'),
    ).toBe(true);
  });
  it('expires without activity even if session polling is stalled', async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue(response(200));
    view();
    await act(async () => {});
    fetchMock.mockImplementation(() => new Promise(() => {}));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60 * 60 * 1000);
    });
    expect(screen.getByRole('status')).toHaveTextContent('sessão terminou');
  });
  it('shows loading and recoverable unavailable state', async () => {
    let resolve: (value: ReturnType<typeof response>) => void = () => {};
    fetchMock.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    view();
    expect(screen.getByRole('status')).toHaveTextContent('Aguarde');
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await act(async () => resolve(response(503)));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Tente novamente',
    );
    fetchMock.mockResolvedValue(response(401));
    await userEvent.click(
      screen.getByRole('button', { name: 'Verificar conexão novamente' }),
    );
    await waitFor(() =>
      expect(screen.queryByRole('alert')).not.toBeInTheDocument(),
    );
  });
});
