import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import type { Quotation } from '../quotations/api';
import {
  QuotationError,
  quotationFeedback,
  quotationRequest,
  quotationLink,
} from '../quotations/api';
import { QuotationEditor } from '../quotations/QuotationEditor';
import { paymentRequest } from '../payments/api';
import type { Payments } from '../payments/api';
import { rentalRequest, rentalStateLabel } from './api';
import type { Rental, RentalRevision } from './api';
import { priceLabel } from '../catalog/api';

async function fetchRental(id: string, signal?: AbortSignal) {
  try {
    return await rentalRequest<Rental>(`/by-quotation/${id}`, signal);
  } catch (problem) {
    if (problem instanceof QuotationError && problem.status === 404)
      return null;
    throw problem;
  }
}

export function RentalChanges({
  quotation,
  onChanged,
}: {
  quotation: Quotation;
  onChanged: () => void;
}) {
  const navigate = useNavigate();
  const [copying, setCopying] = useState(false);
  const [rental, setRental] = useState<Rental | null>(null);
  const [loading, setLoading] = useState(true);
  const [readKnown, setReadKnown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reason, setReason] = useState('');
  const [approved, setApproved] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [editor, setEditor] = useState<{
    quotation: Quotation;
    revision: RentalRevision;
  } | null>(null);
  const pending = useRef<object | null>(null);
  const feedback = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const inFlight = useRef(false);

  async function load(signal?: AbortSignal) {
    const value = await fetchRental(quotation.id, signal);
    if (!signal?.aborted) {
      setRental(value);
      setReadKnown(true);
    }
    return value;
  }
  useEffect(() => {
    const controller = new AbortController();
    void fetchRental(quotation.id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setRental(value);
          setReadKnown(true);
        }
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(quotationFeedback(problem));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [quotation.id, quotation.current_version]);
  useEffect(() => {
    if (error || notice) feedback.current?.focus();
  }, [error, notice]);

  async function prepare(mode: 'change' | 'resume') {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const [current, financial, currentRental] = await Promise.all([
        quotationRequest<Quotation>(`/${quotation.id}`),
        paymentRequest<Payments>(quotation.id),
        load(),
      ]);
      setEditor({
        quotation: current,
        revision: {
          id: currentRental?.id,
          mode,
          expected_rental_version: currentRental?.version ?? 0,
          expected_quotation_version: current.current_version,
          expected_financial_version: financial.financial_version,
          financial,
        },
      });
    } catch (problem) {
      setError(quotationFeedback(problem));
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    if (!rental || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    const command = pending.current ?? {
      request_id: crypto.randomUUID(),
      reason,
      approved,
      expected_rental_version: rental.version,
      expected_quotation_version: rental.current_financial.quotation_version,
      expected_financial_version: rental.current_financial.financial_version,
    };
    pending.current = command;
    try {
      const saved = await rentalRequest<Rental>(
        `/${rental.id}/cancellations`,
        undefined,
        command,
      );
      setRental(saved);
      setUnknown(false);
      pending.current = null;
      setCancelling(false);
      setNotice(
        saved.state === 'cancelled'
          ? 'Cancelamento aprovado registrado. Alocação desta reserva liberada; dinheiro e devoluções continuam no financeiro.'
          : saved.allocations.length
            ? 'Solicitação registrada. A reserva e o estoque continuam comprometidos até a aprovação da equipe.'
            : 'Solicitação registrada. A locação permanece em revisão, sem alocação; a equipe ainda não aprovou o cancelamento.',
      );
      onChanged();
      heading.current?.focus();
    } catch (problem) {
      setError(quotationFeedback(problem));
      if (problem instanceof QuotationError && problem.status < 500) {
        pending.current = null;
        setUnknown(false);
        await load().catch(() => undefined);
      } else setUnknown(true);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  async function copy() {
    if (!rental) return;
    setBusy(true);
    setError('');
    try {
      await rentalRequest(`/${rental.id}/copy-preview`, undefined, {
        expected_rental_version: rental.version,
        expected_quotation_version: rental.current_financial.quotation_version,
        expected_financial_version: rental.current_financial.financial_version,
      });
      setCopying(true);
    } catch (problem) {
      setError(quotationFeedback(problem));
    } finally {
      setBusy(false);
    }
  }
  if (copying)
    return (
      <QuotationEditor
        copyFrom={quotation}
        onCancel={() => setCopying(false)}
        onSaved={(value) => navigate(quotationLink(value.id))}
      />
    );
  if (editor)
    return (
      <QuotationEditor
        initial={editor.quotation}
        rentalRevision={editor.revision}
        onCancel={() => {
          setEditor(null);
          heading.current?.focus();
        }}
        onSaved={() => {
          const resumed = editor.revision.mode === 'resume';
          setEditor(null);
          setNotice(
            resumed
              ? 'Locação retomada em revisão. Confira o sinal e use Confirmar reserva para nova checagem de estoque.'
              : 'Alteração registrada pelo servidor, com nova revisão e histórico.',
          );
          void load().catch((problem: unknown) =>
            setError(quotationFeedback(problem)),
          );
          onChanged();
        }}
      />
    );
  return (
    <section className="catalog-section" aria-labelledby="rental-changes-title">
      <h3 id="rental-changes-title" tabIndex={-1} ref={heading}>
        Alterações no aluguel do cliente
      </h3>
      {loading && <p role="status">Consultando alterações da locação…</p>}
      <div ref={feedback} tabIndex={-1}>
        {error && (
          <p role="alert" className="auth-feedback">
            {error}
          </p>
        )}
        {notice && <p role="status">{notice}</p>}
      </div>
      {rental && (
        <>
          <p>
            <strong>
              {rentalStateLabel[rental.state]} · versão {rental.version}
            </strong>
          </p>
          <dl className="catalog-attributes">
            <div>
              <dt>Estoque</dt>
              <dd>
                {rental.allocations?.length
                  ? 'Alocação ativa'
                  : 'Sem alocação de estoque'}
              </dd>
            </div>
            <div>
              <dt>Dinheiro líquido</dt>
              <dd>{priceLabel(rental.current_financial.net_received)}</dd>
            </div>
            <div>
              <dt>Saldo financeiro</dt>
              <dd>{priceLabel(rental.current_financial.remaining)}</dd>
            </div>
            <div>
              <dt>Excesso pendente de decisão</dt>
              <dd>{priceLabel(rental.current_financial.excess)}</dd>
            </div>
            <div>
              <dt>Revisão para assinatura</dt>
              <dd>
                Comercial v{rental.signature_commercial_version}; nova
                assinatura após alteração, quando contratos estiverem
                disponíveis.
              </dd>
            </div>
          </dl>
        </>
      )}
      {!loading && readKnown && !rental && !quotation.expired && (
        <p>
          As alterações da reserva ficam disponíveis após confirmação. O
          orçamento atual pode receber uma nova revisão comercial.
        </p>
      )}
      {unknown && (
        <p role="status">
          Resultado desconhecido. Reconcile o mesmo cancelamento antes de editar
          ou enviar outra ação.
        </p>
      )}
      <div className="catalog-actions">
        {rental && ['confirmed', 'review', 'out'].includes(rental.state) && (
          <button
            className="auth-button"
            disabled={busy || unknown || cancelling}
            onClick={() => void prepare('change')}
          >
            Alterar locação
          </button>
        )}
        {(rental?.state === 'cancelled' ||
          (readKnown && !rental && quotation.expired)) && (
          <button
            className="auth-button"
            disabled={busy || unknown}
            onClick={() => void prepare('resume')}
          >
            Revisar e retomar
          </button>
        )}
        {rental && ['confirmed', 'review'].includes(rental.state) && (
          <button
            className="auth-retry"
            disabled={busy || unknown}
            onClick={() => setCancelling(true)}
          >
            Registrar cancelamento
          </button>
        )}
        {rental?.state === 'completed' && (
          <button
            className="auth-button"
            disabled={busy || unknown}
            onClick={() => void copy()}
          >
            Criar nova proposta baseada nesta
          </button>
        )}
        <button
          className="auth-retry"
          disabled={busy || unknown}
          onClick={() => {
            setError('');
            void load().catch((problem: unknown) =>
              setError(quotationFeedback(problem)),
            );
          }}
        >
          Reconsultar alterações
        </button>
      </div>
      {rental?.state === 'out' && (
        <p>
          Após saída, ajuste apenas preço/motivo ou extensão com capacidade.
          Complementos exigem nova locação; devolução antecipada depende da
          conferência real.
        </p>
      )}
      {rental?.state === 'completed' && (
        <p>
          Locação concluída não reabre. Uma nova proposta terá novo ID, preços
          atuais revisados e nenhum pagamento transferido.
        </p>
      )}
      {cancelling && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void cancel();
          }}
        >
          <fieldset disabled={busy || unknown}>
            <legend>Decisão de cancelamento antes da saída</legend>
            <label>
              Motivo do cancelamento
              <textarea
                required
                maxLength={1000}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <label className="quotation-checkbox">
              <input
                type="checkbox"
                checked={approved}
                onChange={(event) => setApproved(event.target.checked)}
              />
              A equipe aprova o cancelamento e a liberação da alocação desta
              reserva
            </label>
            <p>
              Sem aprovação, registra somente a solicitação. Cancelar não
              devolve dinheiro nem elimina saldo ou pendências.
            </p>
          </fieldset>
          {unknown ? (
            <button
              type="button"
              className="auth-button"
              disabled={busy}
              onClick={() => void cancel()}
            >
              Reconciliar o mesmo cancelamento
            </button>
          ) : (
            <div className="catalog-actions">
              <button className="auth-button" disabled={busy || !reason.trim()}>
                {busy
                  ? 'Registrando…'
                  : approved
                    ? 'Confirmar cancelamento aprovado'
                    : 'Registrar solicitação sem liberar estoque'}
              </button>
              <button
                type="button"
                className="auth-retry"
                disabled={busy}
                onClick={() => setCancelling(false)}
              >
                Voltar sem cancelar
              </button>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
