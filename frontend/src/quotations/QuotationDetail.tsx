import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { priceLabel } from '../catalog/api';
import { customerLink } from '../customers/api';
import {
  dateLabels,
  quotationFeedback,
  quotationLink,
  quotationRequest,
} from './api';
import type { Quotation } from './api';
import { OfferSummary } from './OfferSummary';
import { FinancialSection } from '../payments/FinancialSection';
import { ConfirmationSection } from '../rentals/ConfirmationSection';
import { RentalChanges } from '../rentals/RentalChanges';

export function QuotationDetail({
  record,
  onEdit,
  onClose,
}: {
  record: Quotation;
  onEdit: () => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(record);
  const [versions, setVersions] = useState<Quotation[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [changed, setChanged] = useState(false);
  const [financialRead, setFinancialRead] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void quotationRequest<Quotation[]>(
      `/${record.id}/versions`,
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) setVersions(value);
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(quotationFeedback(problem));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [record.id]);
  async function consult() {
    setLoading(true);
    setError('');
    try {
      const latest = await quotationRequest<Quotation>(
        `/${record.id}${selected.version === selected.current_version ? '' : `/versions/${selected.version}`}`,
      );
      setChanged(
        JSON.stringify(latest.capacity) !== JSON.stringify(selected.capacity),
      );
      setSelected(latest);
      setVersions(
        await quotationRequest<Quotation[]>(`/${record.id}/versions`),
      );
    } catch (problem) {
      setError(quotationFeedback(problem));
    } finally {
      setLoading(false);
    }
  }
  return (
    <section className="catalog-panel" aria-labelledby="quotation-detail-title">
      <div className="catalog-panel-heading">
        <div>
          <span className="section-kicker">
            ORÇAMENTO · REVISÃO {selected.version}
          </span>
          <h2 id="quotation-detail-title" tabIndex={-1} ref={heading}>
            Acordo comercial
          </h2>
          <p className="quotation-id">{record.id}</p>
        </div>
        <div className="catalog-actions">
          <button className="auth-retry" onClick={onClose}>
            Voltar à lista
          </button>
          <button
            className="auth-button"
            onClick={onEdit}
            disabled={Boolean(selected.rental)}
          >
            Criar nova revisão
          </button>
        </div>
      </div>
      <p>
        <Link to={customerLink(record.customer_id)}>
          Abrir cliente vinculado
        </Link>{' '}
        · <Link to={quotationLink(record.id)}>Link deste orçamento</Link>
      </p>
      <dl className="catalog-attributes">
        {Object.entries(dateLabels).map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{selected[key as keyof typeof dateLabels]}</dd>
          </div>
        ))}
        {(['pickup_time', 'event_time', 'return_time'] as const).map(
          (key, index) => (
            <div key={key}>
              <dt>
                {
                  [
                    'Horário da retirada',
                    'Horário do evento',
                    'Horário da devolução',
                  ][index]
                }
              </dt>
              <dd>{selected[key] ?? 'Não informado'}</dd>
            </div>
          ),
        )}
      </dl>
      <h3>Itens acordados nesta revisão</h3>
      <ul className="quotation-capacity">
        {selected.lines.map((line) => (
          <li key={line.id}>
            <strong>{line.name}</strong>
            <span>
              {line.quantity} × {priceLabel(line.unit_price)} · fonte v
              {line.source_version}
            </span>
            <ul>
              {line.items.map((item) => (
                <li key={item.product_id}>
                  {item.quantity} × {item.name} · fonte v{item.source_version}
                </li>
              ))}
            </ul>
            {line.negotiation_reason && (
              <p>Negociação: {line.negotiation_reason}</p>
            )}
          </li>
        ))}
      </ul>
      {selected.discount && (
        <p>
          Desconto{' '}
          {selected.discount.kind === 'percent'
            ? `${selected.discount.value}%`
            : priceLabel(selected.discount.value)}{' '}
          · {selected.discount.reason ?? 'Sem desconto positivo'}
        </p>
      )}
      <OfferSummary offer={selected} showPaymentEstimate={!selected.rental} />
      <FinancialSection
        quotationId={record.id}
        refreshVersion={financialRead}
      />
      <ConfirmationSection
        key={`${record.id}:${selected.current_version}:${selected.rental?.version ?? 0}`}
        quotation={selected}
        onConfirmed={() => void consult()}
        onFinancialRefresh={() => setFinancialRead((version) => version + 1)}
      />
      {selected.version === selected.current_version && (
        <RentalChanges
          key={`${record.id}:${selected.current_version}`}
          quotation={selected}
          onChanged={() => {
            void consult();
            setFinancialRead((version) => version + 1);
          }}
        />
      )}
      <button
        className="auth-retry"
        disabled={loading}
        onClick={() => void consult()}
      >
        Reconsultar estoque cadastral
      </button>
      {changed && (
        <p role="status">
          O estoque cadastral mudou desde a última consulta. Os valores e a
          composição acordados foram preservados.
        </p>
      )}
      <section className="catalog-section" aria-labelledby="quotation-versions">
        <h3 id="quotation-versions">Histórico de revisões</h3>
        {loading && <p role="status">Consultando revisões…</p>}
        {error && (
          <div role="alert" className="auth-feedback">
            {error}
            <button className="auth-retry" onClick={() => void consult()}>
              Tentar novamente
            </button>
          </div>
        )}
        <ul className="catalog-history">
          {versions.map((version) => (
            <li key={version.version}>
              <div>
                <strong>
                  Revisão {version.version} · {priceLabel(version.total)}
                </strong>
                <button
                  className="auth-retry"
                  onClick={() => {
                    setSelected(version);
                    setChanged(false);
                  }}
                >
                  Consultar revisão {version.version}
                </button>
              </div>
              <p>
                {version.reason ?? 'Proposta inicial'} ·{' '}
                {version.expired ? 'Vencido' : 'Validade vigente'}
              </p>
              <p>
                Autor {version.actor_id} · sessão {version.session_id}
              </p>
              <time dateTime={version.revised_at}>
                {new Date(version.revised_at).toLocaleString('pt-BR', {
                  timeZone: 'America/Sao_Paulo',
                })}
              </time>
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}
