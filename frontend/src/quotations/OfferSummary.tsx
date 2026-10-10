import { priceLabel } from '../catalog/api';
import type { Offer } from './api';

export function OfferSummary({ offer }: { offer: Offer }) {
  return (
    <section
      className="quotation-summary"
      aria-label="Prévia comercial do servidor"
    >
      <h3>Valores por locação</h3>
      <dl className="catalog-attributes">
        {(
          [
            ['Subtotal', offer.subtotal],
            ['Desconto calculado', offer.discount_amount],
            ['Total', offer.total],
            ['Sinal previsto', offer.estimated_deposit],
            ['Saldo previsto', offer.estimated_balance],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{priceLabel(value)}</dd>
          </div>
        ))}
      </dl>
      <p>
        Sinal e saldo são previsões comerciais; registrar e conciliar
        recebimentos são operações separadas.
      </p>
      <p className="quotation-scope">
        Orçamento não reserva estoque. A consulta considera compromissos
        simultâneos no período; confirmar sempre faz nova checagem.
      </p>
      <p>
        <strong>
          {offer.expired
            ? 'Vencido · requer nova revisão antes de fechar'
            : 'Validade comercial vigente'}
        </strong>
      </p>
      <h3>Demanda e estoque apto cadastral</h3>
      <ul className="quotation-capacity">
        {offer.capacity.map((item) => (
          <li key={item.product_id}>
            <strong>{item.name}</strong>
            <span>
              Demanda {item.demand} · Apto {item.apt}
            </span>
            <span>
              Disponível no período {item.available ?? item.apt} · pico
              comprometido {item.committed ?? 0}
            </span>
            <span
              className={
                item.shortage
                  ? 'catalog-badge catalog-badge--warning'
                  : 'catalog-badge'
              }
            >
              {item.shortage
                ? `Faltam ${item.shortage} · pendência comercial`
                : 'Sem falta cadastral'}
            </span>
          </li>
        ))}
      </ul>
      {offer.stock_pending && (
        <p role="status">
          Você pode salvar com esta pendência. Combine a solução com a equipe;
          não prometa disponibilidade.
        </p>
      )}
      <small>
        Consulta cadastral:{' '}
        {new Date(offer.capacity_checked_at).toLocaleString('pt-BR', {
          timeZone: 'America/Sao_Paulo',
        })}
        . Devolução inclui o dia previsto; planejamento a partir de{' '}
        {offer.planning_available_from}.
      </small>
    </section>
  );
}
