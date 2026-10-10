import { useEffect, useRef } from 'react';
import { customerLink, fieldLabels } from './api';
import type { CustomerDetail as Detail } from './api';
import { CustomerQuotations } from '../quotations/CustomerQuotations';

export function CustomerDetail({
  record,
  onEdit,
  onClose,
}: {
  record: Detail;
  onEdit: () => void;
  onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const values = {
    name: record.name,
    phone: record.phone,
    email: record.email,
    notes: record.notes,
    cpf: record.cpf,
    rg: record.rg,
    ...record.address,
  };
  return (
    <section
      className="catalog-panel"
      aria-labelledby="customer-detail-heading"
    >
      <div className="catalog-panel-heading">
        <div>
          <span className="section-kicker">
            PESSOA FÍSICA · VERSÃO {record.version}
          </span>
          <h2 id="customer-detail-heading" ref={heading} tabIndex={-1}>
            {record.name}
          </h2>
        </div>
        <div className="catalog-actions">
          <button className="auth-retry" onClick={onClose}>
            Voltar à lista
          </button>
          <button className="auth-button" onClick={onEdit}>
            Editar cliente
          </button>
        </div>
      </div>
      <dl className="catalog-attributes">
        {Object.entries(values).map(([key, value]) => (
          <div key={key}>
            <dt>{fieldLabels[key as keyof typeof fieldLabels]}</dt>
            <dd>{value || 'Não informado'}</dd>
          </div>
        ))}
      </dl>
      <CustomerQuotations customerId={record.id} />
      <a className="catalog-back" href={customerLink(record.id)}>
        Link deste cliente
      </a>
      <section className="catalog-section" aria-labelledby="customer-history">
        <h3 id="customer-history">Histórico do cadastro</h3>
        <ul className="catalog-history">
          {record.history.map((entry) => (
            <li key={entry.id}>
              <div>
                <strong>Versão {entry.version}</strong>
                <time dateTime={entry.created_at}>
                  {new Date(entry.created_at).toLocaleString('pt-BR')}
                </time>
              </div>
              <p>
                {entry.version === 1
                  ? 'Cliente cadastrado'
                  : 'Cadastro atualizado'}{' '}
                ·{' '}
                {entry.changed_fields
                  .map(
                    (field) =>
                      fieldLabels[field as keyof typeof fieldLabels] ?? field,
                  )
                  .join(', ') || 'Nenhum campo alterado'}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}
