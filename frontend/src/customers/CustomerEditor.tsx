import { useEffect, useRef, useState } from 'react';
import {
  addressLabels,
  CustomerError,
  customerFeedback,
  customerLink,
  customerRequest,
  fieldLabels,
} from './api';
import type { CustomerDetail } from './api';

type Draft = {
  name: string;
  phone: string;
  email: string;
  notes: string;
  cpf: string;
  rg: string;
} & Record<keyof typeof addressLabels, string>;
function draftOf(record?: CustomerDetail): Draft {
  return {
    name: record?.name ?? '',
    phone: record?.phone ?? '',
    email: record?.email ?? '',
    notes: record?.notes ?? '',
    cpf: record?.cpf ?? '',
    rg: record?.rg ?? '',
    postal_code: record?.address?.postal_code ?? '',
    street: record?.address?.street ?? '',
    number: record?.address?.number ?? '',
    complement: record?.address?.complement ?? '',
    neighborhood: record?.address?.neighborhood ?? '',
    city: record?.address?.city ?? '',
    state: record?.address?.state ?? '',
  };
}

export function CustomerEditor({
  initial,
  onSaved,
  onCancel,
}: {
  initial?: CustomerDetail;
  onSaved: (record: CustomerDetail) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState(() => draftOf(initial));
  const [version, setVersion] = useState(initial?.version);
  const [current, setCurrent] = useState<CustomerDetail | null>(null);
  const [failure, setFailure] = useState<CustomerError | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const alert = useRef<HTMLDivElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  useEffect(() => {
    if (error) alert.current?.focus();
  }, [error]);
  async function save(acknowledged: string[] = []) {
    setBusy(true);
    setError('');
    setFailure(null);
    const address = Object.fromEntries(
      Object.keys(addressLabels).map((key) => [
        key,
        draft[key as keyof Draft].trim() || null,
      ]),
    );
    try {
      const result = await customerRequest<CustomerDetail>(
        initial ? `/${initial.id}` : '',
        initial ? 'PATCH' : 'POST',
        {
          name: draft.name,
          phone: draft.phone,
          email: draft.email.trim() || null,
          notes: draft.notes.trim() || null,
          cpf: draft.cpf.trim() || null,
          rg: draft.rg.trim() || null,
          address,
          acknowledged_shared_contact: acknowledged,
          ...(initial ? { expected_version: version } : {}),
        },
      );
      onSaved(result);
    } catch (problem) {
      setError(customerFeedback(problem));
      if (problem instanceof CustomerError) setFailure(problem);
    } finally {
      setBusy(false);
    }
  }
  async function consult() {
    if (!initial) return;
    setBusy(true);
    try {
      setCurrent(
        await customerRequest<CustomerDetail>(`/${initial.id}`, 'GET'),
      );
    } catch (problem) {
      setError(customerFeedback(problem));
    } finally {
      setBusy(false);
    }
  }
  function input(
    field: keyof Draft,
    maxLength: number,
    required = false,
    type = 'text',
  ) {
    return (
      <label key={field}>
        {fieldLabels[field]}
        {required ? ' *' : ''}
        <input
          name={field}
          type={type}
          required={required}
          maxLength={maxLength}
          value={draft[field]}
          autoComplete="off"
          onChange={(event) => {
            setDraft({ ...draft, [field]: event.target.value });
            if (field === 'phone' || field === 'cpf') {
              setFailure(null);
              setError('');
            }
          }}
        />
      </label>
    );
  }
  return (
    <section
      className="catalog-panel"
      aria-labelledby="customer-editor-heading"
    >
      <div className="catalog-panel-heading">
        <div>
          <span className="section-kicker">
            CADASTRO PROGRESSIVO · PESSOA FÍSICA
          </span>
          <h2 id="customer-editor-heading" tabIndex={-1} ref={heading}>
            {initial ? `Editar ${initial.name}` : 'Novo cliente'}
          </h2>
        </div>
        <button className="auth-retry" disabled={busy} onClick={onCancel}>
          Cancelar
        </button>
      </div>
      <p className="catalog-help">
        Comece com nome e telefone. Os documentos e o endereço podem vir depois.
      </p>
      {error && (
        <div
          role="alert"
          tabIndex={-1}
          ref={alert}
          className="catalog-conflict"
        >
          <p>{error}</p>
          {failure?.existingIds.map((id, index) => (
            <p key={id}>
              <a
                href={customerLink(id)}
                target="_blank"
                rel="noopener noreferrer"
              >
                Consultar cadastro {index + 1} (nova aba)
              </a>
            </p>
          ))}
          {failure?.code === 'shared_contact' && (
            <button
              className="auth-retry"
              disabled={busy}
              onClick={() => void save(failure.existingIds)}
            >
              Confirmar pessoa distinta e salvar
            </button>
          )}
          {failure?.code === 'stale_version' && (
            <>
              <p>
                Seu rascunho continua abaixo. Compare antes de salvar novamente.
              </p>
              <button
                className="auth-retry"
                disabled={busy}
                onClick={() => void consult()}
              >
                Consultar versão atual
              </button>
              {current && (
                <div className="customer-comparison">
                  <h3>Versão atual {current.version}</h3>
                  <dl className="catalog-attributes">
                    {Object.entries(draftOf(current)).map(([key, value]) => (
                      <div key={key}>
                        <dt>{fieldLabels[key as keyof Draft]}</dt>
                        <dd>{value || 'Não informado'}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="catalog-actions">
                    <button
                      className="auth-retry"
                      onClick={() => {
                        setVersion(current.version);
                        setFailure(null);
                        setError('');
                      }}
                    >
                      Manter meu rascunho e usar versão atual
                    </button>
                    <button
                      className="auth-retry"
                      onClick={() => {
                        setDraft(draftOf(current));
                        setVersion(current.version);
                        setFailure(null);
                        setError('');
                      }}
                    >
                      Recarregar dados atuais
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
      <form
        className="catalog-form"
        aria-busy={busy}
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={busy}>
          <legend className="sr-only">Dados do cliente</legend>
          <div className="catalog-form-grid">
            {input('name', 200, true)}
            {input('phone', 50, true, 'tel')}
            {input('email', 320, false, 'email')}
            <label>
              <span id="customer-notes-label">Observações</span>
              <textarea
                aria-labelledby="customer-notes-label"
                name="notes"
                rows={3}
                maxLength={4000}
                value={draft.notes}
                onChange={(event) =>
                  setDraft({ ...draft, notes: event.target.value })
                }
              />
            </label>
          </div>
          <details className="catalog-optionals">
            <summary>Documentos e endereço (opcionais)</summary>
            <p className="catalog-help">
              Preencha apenas o que já foi informado. O cadastro inicial não
              exige documentação completa.
            </p>
            <div className="catalog-form-grid">
              {input('cpf', 14)}
              {input('rg', 30)}
              {input('postal_code', 9)}
              {input('street', 200)}
              {input('number', 30)}
              {input('complement', 200)}
              {input('neighborhood', 100)}
              {input('city', 100)}
              {input('state', 2)}
            </div>
          </details>
        </fieldset>
        <div className="catalog-actions">
          <button className="auth-button" disabled={busy} type="submit">
            {busy ? 'Salvando…' : 'Salvar cliente'}
          </button>
        </div>
      </form>
    </section>
  );
}
