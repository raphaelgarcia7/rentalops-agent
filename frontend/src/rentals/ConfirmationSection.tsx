import { useEffect, useRef, useState } from 'react';
import { paymentRequest } from '../payments/api';
import type { Payments } from '../payments/api';
import {
  QuotationError,
  quotationFeedback,
  quotationRequest,
} from '../quotations/api';
import type { Quotation } from '../quotations/api';
import { rentalRequest } from './api';
import type { History, Preview, Rental } from './api';

type Command = {
  request_id: string;
  expected_quotation_version: number;
  expected_financial_version: number;
};

async function snapshot(id: string, signal?: AbortSignal) {
  let rental: Rental;
  try {
    rental = await rentalRequest<Rental>(`/by-quotation/${id}`, signal);
  } catch (problem) {
    if (problem instanceof QuotationError && problem.status === 404)
      return null;
    throw problem;
  }
  const history = await rentalRequest<History>(
    `/${rental.id}/history?page=1&page_size=10`,
    signal,
  );
  return { rental, history };
}

export function ConfirmationSection({
  quotation,
  onConfirmed,
  onFinancialRefresh,
}: {
  quotation: Quotation;
  onConfirmed: () => void;
  onFinancialRefresh?: () => void;
}) {
  const [rental, setRental] = useState<Rental | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [command, setCommand] = useState<Command | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasConsulted, setHasConsulted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [conflicts, setConflicts] = useState<Quotation['capacity']>([]);
  const inFlight = useRef(false);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const feedback = useRef<HTMLDivElement>(null);

  async function loadRental(signal?: AbortSignal) {
    const value = await snapshot(quotation.id, signal);
    if (!signal?.aborted) setHasConsulted(true);
    if (value && !signal?.aborted) {
      setRental(value.rental);
      setHistory(value.history);
    }
    return value !== null;
  }
  useEffect(() => {
    const controller = new AbortController();
    void snapshot(quotation.id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setHasConsulted(true);
        if (value && !controller.signal.aborted) {
          setRental(value.rental);
          setHistory(value.history);
        }
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(quotationFeedback(problem));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [quotation.id]);
  useEffect(() => {
    if (preview) confirmButton.current?.focus();
  }, [preview]);
  useEffect(() => {
    if (error || notice) feedback.current?.focus();
  }, [error, notice]);

  async function prepare() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    setPreview(null);
    setCommand(null);
    setConflicts([]);
    try {
      if (await loadRental()) return;
      const [current, financial] = await Promise.all([
        quotationRequest<Quotation>(`/${quotation.id}`),
        paymentRequest<Payments>(quotation.id, ''),
      ]);
      if (current.current_version !== quotation.version)
        throw new QuotationError(
          409,
          'A proposta mudou. Reconsulte a revisão vigente antes de confirmar.',
        );
      const payload = {
        expected_quotation_version: current.current_version,
        expected_financial_version: financial.financial_version,
      };
      const value = await quotationRequest<Preview>(
        `/${quotation.id}/confirmation-preview`,
        payload,
      );
      setPreview(value);
      setCommand({ ...payload, request_id: crypto.randomUUID() });
    } catch (problem) {
      setError(quotationFeedback(problem));
    } finally {
      onFinancialRefresh?.();
      inFlight.current = false;
      setBusy(false);
      setLoading(false);
    }
  }
  async function confirm() {
    if (!command || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const value = await quotationRequest<Rental>(
        `/${quotation.id}/confirm`,
        command,
      );
      setRental(value);
      setUnknown(false);
      setCommand(null);
      setPreview(null);
      setNotice(
        'Reserva confirmada pelo servidor. Estoque alocado para o período.',
      );
      onConfirmed();
      await loadRental().catch(() => {
        setError(
          'Reserva confirmada. O histórico está indisponível; reconsulte a locação.',
        );
      });
    } catch (problem) {
      if (problem instanceof QuotationError && problem.status < 500) {
        setError(quotationFeedback(problem));
        setConflicts(problem.capacity ?? []);
        setUnknown(false);
        setCommand(null);
        setPreview(null);
        if (problem.code === 'already_confirmed') await loadRental();
      } else {
        setError(quotationFeedback(null));
        setUnknown(true);
      }
    } finally {
      onFinancialRefresh?.();
      inFlight.current = false;
      setBusy(false);
    }
  }
  return (
    <section
      className="catalog-section"
      aria-labelledby="rental-confirmation-title"
    >
      <h3 id="rental-confirmation-title">Reserva e estoque do período</h3>
      <p>
        Recebimento, conciliação e confirmação são ações separadas. A
        confirmação revalida o sinal e o estoque; a prévia não garante
        disponibilidade.
      </p>
      {loading && <p role="status">Consultando locação…</p>}
      <div ref={feedback} tabIndex={-1}>
        {error && (
          <p className="auth-feedback" role="alert">
            {error}
          </p>
        )}
        {notice && <p role="status">{notice}</p>}
        {conflicts.length > 0 && (
          <ul className="quotation-capacity">
            {conflicts.map((item) => (
              <li key={item.product_id}>
                <strong>{item.name}</strong>
                <span>
                  Demanda {item.demand} · disponível {item.available} · faltam{' '}
                  {item.shortage}
                </span>
                {item.conflicts?.map((interval) => (
                  <span key={`${interval.start}:${interval.end}`}>
                    Conflito de {interval.start} a {interval.end} · faltam{' '}
                    {interval.shortage}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        )}
      </div>
      {rental ? (
        <>
          <p>
            <strong>Reserva confirmada · locação v{rental.version}</strong>
          </p>
          <p className="quotation-id">Locação {rental.id}</p>
          <p>
            Proposta v{rental.quotation_version} · financeiro v
            {rental.financial_version} · conferência{' '}
            {new Date(rental.checked_at).toLocaleString('pt-BR', {
              timeZone: 'America/Sao_Paulo',
            })}
          </p>
          <p>
            Alterações comerciais serão feitas no fluxo de alteração da locação.
            Retirada e devolução ainda não estão disponíveis.
          </p>
          {rental.inventory_pending && (
            <p role="status">
              Pendência de estoque: a equipe precisa combinar uma solução. A
              reserva foi preservada.
            </p>
          )}
          {rental.financial_pending && (
            <p role="status">
              Pendência financeira após correção ou devolução de dinheiro. A
              alocação foi preservada.
            </p>
          )}
          <ul className="catalog-history">
            {rental.pending.map((item) => (
              <li key={item.id}>
                {item.kind === 'inventory' ? 'Estoque' : 'Financeiro'} · origem{' '}
                {item.source} · versão {item.source_version}
                {item.resolved
                  ? ' · resolvida pela confirmação'
                  : ' · pendente'}
              </li>
            ))}
          </ul>
          <h4>Histórico da locação</h4>
          {!history ? (
            <p role="status">Consultando histórico…</p>
          ) : (
            <>
              <ul className="catalog-history">
                {history.items.map((item) => (
                  <li key={item.id}>
                    Confirmação · versão {item.version} · autor {item.actor_id}{' '}
                    ·{' '}
                    <time dateTime={item.created_at}>
                      {new Date(item.created_at).toLocaleString('pt-BR', {
                        timeZone: 'America/Sao_Paulo',
                      })}
                    </time>
                  </li>
                ))}
              </ul>
              <div className="catalog-actions">
                <button
                  className="auth-retry"
                  disabled={busy || history.page === 1}
                  onClick={() =>
                    void rentalRequest<History>(
                      `/${rental.id}/history?page=${history.page - 1}&page_size=10`,
                    )
                      .then(setHistory)
                      .catch((problem: unknown) =>
                        setError(quotationFeedback(problem)),
                      )
                  }
                >
                  Histórico anterior
                </button>
                <button
                  className="auth-retry"
                  disabled={
                    busy || history.page * history.page_size >= history.total
                  }
                  onClick={() =>
                    void rentalRequest<History>(
                      `/${rental.id}/history?page=${history.page + 1}&page_size=10`,
                    )
                      .then(setHistory)
                      .catch((problem: unknown) =>
                        setError(quotationFeedback(problem)),
                      )
                  }
                >
                  Mais histórico
                </button>
              </div>
            </>
          )}
          <button
            className="auth-retry"
            disabled={busy}
            onClick={() => void prepare()}
          >
            Reconsultar locação
          </button>
        </>
      ) : (
        <>
          {!loading && hasConsulted && !unknown && (
            <p>Nenhuma reserva confirmada para este orçamento.</p>
          )}
          <button
            className="auth-retry"
            disabled={busy || loading || unknown}
            onClick={() => void prepare()}
          >
            Consultar confirmação
          </button>
          {preview && (
            <>
              <p>
                <strong>
                  {preview.deposit_valid
                    ? 'Sinal validado'
                    : 'Sinal ainda não validado'}{' '}
                  · proposta v{preview.quotation_version} · financeiro v
                  {preview.financial_version}
                </strong>
              </p>
              <ul className="quotation-capacity">
                {preview.capacity.map((item) => (
                  <li key={item.product_id}>
                    <strong>{item.name}</strong>
                    <span>
                      Demanda {item.demand} · disponível no período{' '}
                      {item.available} · apto físico {item.apt}
                    </span>
                    {item.shortage > 0 && (
                      <span>
                        Faltam {item.shortage}. Combine a solução com a equipe.
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              {preview.pending && (
                <p role="status">
                  Há pendência de sinal ou estoque. Recebimentos continuam
                  registrados; não prometa a reserva.
                </p>
              )}
            </>
          )}
          {(preview || unknown) && (
            <button
              className="auth-button"
              ref={confirmButton}
              disabled={busy || (!unknown && preview?.pending)}
              onClick={() => void confirm()}
            >
              {busy
                ? 'Confirmando…'
                : unknown
                  ? 'Reconciliar a mesma confirmação'
                  : 'Confirmar reserva'}
            </button>
          )}
        </>
      )}
    </section>
  );
}
