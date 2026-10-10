import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { priceLabel } from '../catalog/api';
import { quotationFeedback, quotationLink, quotationRequest } from './api';
import type { QuotationPage } from './api';
import { rentalStateLabel } from '../rentals/api';

export function CustomerQuotations({ customerId }: { customerId: string }) {
  const [data, setData] = useState<QuotationPage | null>(null);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void quotationRequest<QuotationPage>(
      '/search',
      { customer_id: customerId, page },
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(quotationFeedback(problem));
      });
    return () => controller.abort();
  }, [customerId, page, refresh]);
  return (
    <section className="catalog-section" aria-labelledby="customer-quotations">
      <h3 id="customer-quotations">Orçamentos deste cliente</h3>
      <p>
        Propostas e suas locações confirmadas. Salvar orçamento não aloca
        estoque.
      </p>
      {error ? (
        <div role="alert">
          {error}
          <button
            className="auth-retry"
            onClick={() => {
              setError('');
              setRefresh((value) => value + 1);
            }}
          >
            Tentar novamente
          </button>
        </div>
      ) : !data ? (
        <p role="status">Consultando orçamentos…</p>
      ) : data.items.length ? (
        <>
          <ul className="catalog-history">
            {data.items.map((item) => (
              <li key={item.id}>
                <Link to={quotationLink(item.id)}>
                  Orçamento {item.id.slice(0, 8)} · revisão {item.version}
                </Link>
                <p>
                  {priceLabel(item.total)} ·{' '}
                  {item.expired
                    ? 'Vencido · requer revisão'
                    : 'Validade vigente'}{' '}
                  · evento {item.event_date}
                </p>
                {item.stock_pending && <p>Pendência de estoque cadastral</p>}
                {item.rental ? (
                  <p>
                    {rentalStateLabel[item.rental.state]} · locação v
                    {item.rental.version}
                    {item.rental.inventory_pending
                      ? ' · pendência de estoque'
                      : ''}
                    {item.rental.financial_pending
                      ? ' · pendência financeira'
                      : ''}
                  </p>
                ) : (
                  <p>Sem reserva confirmada</p>
                )}
              </li>
            ))}
          </ul>
          <div className="catalog-actions">
            <button
              className="auth-retry"
              disabled={page === 1}
              onClick={() => setPage((value) => value - 1)}
            >
              Orçamentos anteriores
            </button>
            <button
              className="auth-retry"
              disabled={page * data.page_size >= data.total}
              onClick={() => setPage((value) => value + 1)}
            >
              Mais orçamentos
            </button>
          </div>
        </>
      ) : (
        <p>Nenhum orçamento registrado.</p>
      )}
    </section>
  );
}
