import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { priceLabel } from '../catalog/api';
import {
  businessToday,
  methods,
  operations,
  PaymentError,
  paymentRequest,
} from './api';
import type { History, Payments, Receipt } from './api';
import './payments.css';

type Mode = 'receipt' | 'reconciliation' | 'correction' | 'refund' | 'proof';
type Prepared = {
  path: string;
  body: object | FormData;
  description: string[];
  quotationVersion: number;
  financialVersion: number;
};
const empty = () => ({
  amount: '',
  method: 'pix',
  business_date: businessToday(),
  observation: '',
  reason: '',
  receipt_id: '',
});
const amount = (value: string) => value.replace(',', '.');
const financialLabels = {
  total: 'Total comercial',
  estimated_deposit: 'Sinal previsto',
  estimated_balance: 'Saldo previsto',
  received: 'Recebido registrado',
  refunded: 'Devolvido registrado',
  net_received: 'Recebido líquido',
  applied_deposit: 'Aplicado ao sinal',
  applied_balance: 'Aplicado ao saldo',
  remaining: 'Total restante',
  balance_remaining: 'Saldo restante',
  pending: 'Pendente de conciliação',
  excess: 'Excedente sem crédito automático',
} as const;

export function FinancialSection({
  quotationId,
  refreshVersion = 0,
}: {
  quotationId: string;
  refreshVersion?: number;
}) {
  const [data, setData] = useState<Payments | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadedVersion, setLoadedVersion] = useState(-1);
  const [readError, setReadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [mode, setMode] = useState<Mode>('receipt');
  const [fields, setFields] = useState(empty);
  const [applications, setApplications] = useState<
    Record<string, { deposit: string; balance: string }>
  >({});
  const [file, setFile] = useState<File | null>(null);
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [unknown, setUnknown] = useState(false);
  const feedback = useRef<HTMLDivElement>(null);
  const confirm = useRef<HTMLButtonElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const readSequence = useRef(0);
  const requestedVersion = useRef(refreshVersion);

  useEffect(() => {
    const controller = new AbortController();
    const sequence = ++readSequence.current;
    requestedVersion.current = refreshVersion;
    void Promise.all([
      paymentRequest<Payments>(quotationId, '', undefined, controller.signal),
      paymentRequest<History>(
        quotationId,
        '/history',
        undefined,
        controller.signal,
      ),
    ])
      .then(([value, events]) => {
        if (!controller.signal.aborted && sequence === readSequence.current) {
          setData(value);
          setHistory(events);
          setReadError('');
        }
      })
      .catch(() => {
        if (!controller.signal.aborted && sequence === readSequence.current)
          setReadError(
            'Não foi possível consultar o financeiro e seu histórico. Reconsulte o financeiro.',
          );
      })
      .finally(() => {
        if (!controller.signal.aborted && sequence === readSequence.current) {
          setLoading(false);
          setLoadedVersion(refreshVersion);
        }
      });
    return () => controller.abort();
  }, [quotationId, refreshVersion]);
  useEffect(() => {
    if (error || notice) feedback.current?.focus();
  }, [error, notice]);
  useEffect(() => {
    if (prepared) confirm.current?.focus();
  }, [prepared]);

  async function refresh(preserveError = false) {
    const sequence = ++readSequence.current;
    const version = requestedVersion.current;
    setLoading(true);
    if (!unknown && !preserveError) setError('');
    try {
      const [value, events] = await Promise.all([
        paymentRequest<Payments>(quotationId),
        paymentRequest<History>(quotationId, '/history'),
      ]);
      if (sequence === readSequence.current) {
        setData(value);
        setHistory(events);
        setReadError('');
      }
    } catch {
      if (sequence === readSequence.current)
        setReadError(
          'Não foi possível consultar o financeiro e seu histórico. Reconsulte o financeiro.',
        );
    } finally {
      if (sequence === readSequence.current) {
        setLoading(false);
        setLoadedVersion(version);
      }
    }
  }
  function changeMode(next: Mode, receipt?: Receipt) {
    setMode(next);
    setPrepared(null);
    setError('');
    setNotice('');
    setFile(null);
    setFields(
      receipt
        ? {
            amount: next === 'correction' ? receipt.amount : '',
            method: receipt.method,
            business_date:
              next === 'correction' ? receipt.business_date : businessToday(),
            observation: receipt.observation ?? '',
            reason: '',
            receipt_id: receipt.id,
          }
        : empty(),
    );
    setApplications(
      Object.fromEntries(
        (data?.receipts ?? []).map((item) => [
          item.id,
          { deposit: item.applied_deposit, balance: item.applied_balance },
        ]),
      ),
    );
    title.current?.focus();
  }
  function edit(key: keyof ReturnType<typeof empty>, value: string) {
    setFields((previous) => ({ ...previous, [key]: value }));
    setPrepared(null);
  }
  function prepare(event: FormEvent) {
    event.preventDefault();
    if (!data) return;
    const base = {
      request_id: crypto.randomUUID(),
      expected_financial_version: data.financial_version,
      expected_quotation_version: data.quotation_version,
    };
    let path = '/receipts';
    let body: object | FormData = {
      ...base,
      amount: amount(fields.amount),
      method: fields.method,
      business_date: fields.business_date,
      observation: fields.observation || null,
    };
    let description = [
      `${operations[mode]}`,
      `Valor: ${priceLabel(amount(fields.amount))}`,
      `Forma: ${methods[fields.method as keyof typeof methods]}`,
      `Data: ${fields.business_date}`,
    ];
    if (mode === 'correction') {
      path = `/receipts/${fields.receipt_id}/corrections`;
      body = { ...body, reason: fields.reason };
    }
    if (mode === 'refund') {
      path = '/refunds';
      body = { ...body, receipt_id: fields.receipt_id, reason: fields.reason };
    }
    if (mode === 'reconciliation') {
      path = '/reconciliations';
      const complete = data.receipts.map((receipt) => ({
        receipt_id: receipt.id,
        deposit: amount(applications[receipt.id]?.deposit ?? '0.00'),
        balance: amount(applications[receipt.id]?.balance ?? '0.00'),
      }));
      body = { ...base, applications: complete, reason: fields.reason };
      description = [
        'Substituir toda a distribuição financeira desta conta.',
        ...complete.map(
          (item, index) =>
            `Recebimento ${index + 1}: sinal ${priceLabel(item.deposit)}, saldo ${priceLabel(item.balance)}`,
        ),
      ];
    }
    if (mode === 'proof') {
      if (!file) return;
      path = `/receipts/${fields.receipt_id}/proofs`;
      const form = new FormData();
      for (const [key, value] of Object.entries(base))
        form.append(key, String(value));
      form.append('file', file);
      body = form;
      description = [
        `Anexar comprovante opcional (${file.size.toLocaleString('pt-BR')} bytes).`,
        'O anexo não valida nem quita o pagamento.',
      ];
    }
    const source = data.receipts.find(
      (receipt) => receipt.id === fields.receipt_id,
    );
    if (source && mode !== 'receipt' && mode !== 'reconciliation') {
      description.unshift(
        `Origem: recebimento ${data.receipts.indexOf(source) + 1} (${source.id}), valor registrado ${priceLabel(source.amount)}, líquido ${priceLabel(source.net)}.`,
      );
    }
    setError('');
    setNotice('');
    setPrepared({
      path,
      body,
      description,
      quotationVersion: data.quotation_version,
      financialVersion: data.financial_version,
    });
  }
  async function save() {
    if (!prepared) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await paymentRequest<Payments>(quotationId, prepared.path, prepared.body);
      setPrepared(null);
      setUnknown(false);
      setNotice(
        'Registro financeiro salvo. Isso não confirma reserva nem aloca estoque.',
      );
      // An idempotent replay is the original result, not necessarily the current account.
      await refresh();
    } catch (problem) {
      if (problem instanceof PaymentError && problem.status < 500) {
        setUnknown(false);
        setPrepared(null);
        setError(problem.message);
        if (problem.status === 409) {
          try {
            await refresh(true);
          } catch {
            /* Preserve the form; a separate read may be retried. */
          }
        }
      } else {
        setUnknown(true);
        setError(
          'Resultado desconhecido. O formulário e a mesma chave foram preservados. Repita a mesma operação para consultar o resultado, sem criar outro recebimento.',
        );
      }
    } finally {
      setBusy(false);
    }
  }
  async function historyPage(page: number) {
    setBusy(true);
    setError('');
    try {
      setHistory(
        await paymentRequest<History>(quotationId, `/history?page=${page}`),
      );
    } catch {
      setError(
        'Não foi possível consultar esta página do histórico. Tente novamente.',
      );
    } finally {
      setBusy(false);
    }
  }
  const refreshing = loading || loadedVersion !== refreshVersion;
  return (
    <section
      className="catalog-section payments-section"
      aria-labelledby="financial-heading"
    >
      <h3 id="financial-heading" ref={title} tabIndex={-1}>
        Financeiro deste orçamento
      </h3>
      <p>
        Recebimento é registrado após conferência manual. Conciliação valida a
        distribuição. Nenhuma destas ações confirma reserva ou garante estoque.
      </p>
      {(readError || error || notice) && (
        <div
          ref={feedback}
          tabIndex={-1}
          role={readError || error ? 'alert' : 'status'}
          className="auth-feedback"
        >
          {readError || error || notice}
        </div>
      )}
      {refreshing && <p role="status">Consultando financeiro…</p>}
      <button
        className="auth-retry"
        disabled={refreshing || busy}
        onClick={() => void refresh()}
      >
        Reconsultar financeiro
      </button>
      {data && !refreshing && !readError && (
        <>
          <p>
            Versão comercial {data.quotation_version} · Financeiro{' '}
            {data.financial_version} · Conferida{' '}
            {data.reconciled_quotation_version ?? 'nenhuma'}
          </p>
          {data.commercial_version_pending && (
            <p role="status" className="auth-feedback">
              A versão comercial mudou. Confira e concilie novamente; a
              validação anterior não quita esta versão.
            </p>
          )}
          <dl className="catalog-attributes">
            {Object.entries(financialLabels).map(([key, label]) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd>{priceLabel(data[key as keyof typeof financialLabels])}</dd>
              </div>
            ))}
          </dl>
          <p>
            <strong>
              {data.fully_paid
                ? 'Financeiro integralmente quitado'
                : data.deposit_validated
                  ? 'Sinal validado em um único recebimento'
                  : 'Sinal não validado'}
            </strong>{' '}
            ·{' '}
            {data.requires_reconciliation
              ? 'Há pendência de conciliação'
              : data.reconciled_quotation_version === null
                ? 'Nenhuma conferência registrada'
                : 'Distribuição conferida'}
          </p>
          {data.receipts.length === 0 && (
            <p>Nenhum recebimento registrado. Comprovante é opcional.</p>
          )}
          <ul className="catalog-history">
            {data.receipts.map((receipt, index) => (
              <li key={receipt.id}>
                <h4>
                  Recebimento {index + 1} · {priceLabel(receipt.amount)} ·{' '}
                  {methods[receipt.method]}
                </h4>
                <p>
                  {receipt.business_date} · revisão {receipt.revision} · autor{' '}
                  {receipt.actor_id}
                </p>
                <p>
                  Líquido {priceLabel(receipt.net)} · sinal{' '}
                  {priceLabel(receipt.applied_deposit)} · saldo{' '}
                  {priceLabel(receipt.applied_balance)} · pendente{' '}
                  {priceLabel(receipt.pending)}
                </p>
                {receipt.observation && <p>{receipt.observation}</p>}
                <div className="catalog-actions">
                  {(['correction', 'refund', 'proof'] as const).map((next) => (
                    <button
                      key={next}
                      className="auth-retry"
                      disabled={busy || unknown}
                      onClick={() => changeMode(next, receipt)}
                    >
                      {next === 'correction'
                        ? 'Corrigir recebimento'
                        : next === 'refund'
                          ? 'Registrar devolução já realizada'
                          : 'Anexar comprovante'}
                    </button>
                  ))}
                </div>
                {receipt.proofs.map((proof, i) => (
                  <p key={proof.id}>
                    <a
                      href={`/api/quotations/${quotationId}/payments/proofs/${proof.id}/download`}
                    >
                      Baixar comprovante {i + 1} do recebimento {index + 1}
                    </a>{' '}
                    · {proof.content_type} ·{' '}
                    {proof.size.toLocaleString('pt-BR')} bytes
                  </p>
                ))}
              </li>
            ))}
          </ul>
          <div className="catalog-actions">
            <button
              className="auth-retry"
              disabled={busy || unknown}
              onClick={() => changeMode('receipt')}
            >
              Novo recebimento
            </button>
            <button
              className="auth-retry"
              disabled={busy || unknown || !data.receipts.length}
              onClick={() => changeMode('reconciliation')}
            >
              Conciliar distribuição completa
            </button>
          </div>
          <form
            className="catalog-form"
            onSubmit={prepare}
            aria-labelledby="financial-form-title"
          >
            <h4 id="financial-form-title">
              {mode === 'receipt'
                ? 'Registrar recebimento conferido'
                : mode === 'reconciliation'
                  ? 'Conferir distribuição completa'
                  : mode === 'correction'
                    ? 'Corrigir dados sem devolver dinheiro'
                    : mode === 'refund'
                      ? 'Registrar dinheiro já devolvido'
                      : 'Anexar comprovante opcional'}
            </h4>
            <fieldset disabled={busy || unknown}>
              {mode === 'reconciliation' ? (
                <>
                  <p>
                    Esta distribuição substitui a anterior. Sinal completo em um
                    único recebimento; dois valores insuficientes não se
                    acumulam. O saldo aceita várias origens.
                  </p>
                  {data.receipts.map((receipt, index) => (
                    <fieldset key={receipt.id}>
                      <legend>
                        Recebimento {index + 1} · líquido{' '}
                        {priceLabel(receipt.net)}
                      </legend>
                      {(['deposit', 'balance'] as const).map((key) => (
                        <label key={key}>
                          {key === 'deposit'
                            ? 'Aplicar ao sinal'
                            : 'Aplicar ao saldo'}{' '}
                          — recebimento {index + 1}
                          <input
                            required
                            inputMode="decimal"
                            pattern="[0-9]+[.,][0-9]{2}"
                            value={applications[receipt.id]?.[key] ?? '0.00'}
                            onChange={(event) => {
                              setPrepared(null);
                              setApplications((previous) => ({
                                ...previous,
                                [receipt.id]: {
                                  deposit:
                                    previous[receipt.id]?.deposit ?? '0.00',
                                  balance:
                                    previous[receipt.id]?.balance ?? '0.00',
                                  [key]: event.target.value,
                                },
                              }));
                            }}
                          />
                        </label>
                      ))}
                    </fieldset>
                  ))}
                </>
              ) : mode === 'proof' ? (
                <label>
                  Comprovante PDF, JPEG ou PNG (até 10.000.000 bytes)
                  <input
                    required
                    type="file"
                    accept="application/pdf,image/jpeg,image/png"
                    onChange={(event) => {
                      setFile(event.target.files?.[0] ?? null);
                      setPrepared(null);
                    }}
                  />
                </label>
              ) : (
                <>
                  <label>
                    Valor em reais
                    <input
                      required
                      inputMode="decimal"
                      pattern="[0-9]+[.,][0-9]{2}"
                      placeholder="200,00"
                      value={fields.amount}
                      onChange={(event) => edit('amount', event.target.value)}
                    />
                  </label>
                  <label>
                    Forma de pagamento
                    <select
                      value={fields.method}
                      onChange={(event) => edit('method', event.target.value)}
                    >
                      {Object.entries(methods).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Data do movimento realizado
                    <input
                      required
                      type="date"
                      max={businessToday()}
                      value={fields.business_date}
                      onChange={(event) =>
                        edit('business_date', event.target.value)
                      }
                    />
                  </label>
                  {mode !== 'refund' && (
                    <label>
                      Observação (opcional)
                      <textarea
                        maxLength={2000}
                        value={fields.observation}
                        onChange={(event) =>
                          edit('observation', event.target.value)
                        }
                      />
                    </label>
                  )}
                </>
              )}
              {mode !== 'receipt' && mode !== 'proof' && (
                <label>
                  Motivo obrigatório
                  <textarea
                    required
                    maxLength={1000}
                    value={fields.reason}
                    onChange={(event) => edit('reason', event.target.value)}
                  />
                </label>
              )}
              <button className="auth-button" type="submit">
                Revisar operação financeira
              </button>
            </fieldset>
          </form>
          {prepared && (
            <section
              className="auth-feedback"
              aria-labelledby="financial-preview"
            >
              <h4 id="financial-preview">Confira antes de registrar</h4>
              <ul>
                {prepared.description.map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
              {fields.reason && <p>Motivo: {fields.reason}</p>}
              <p>
                Versão comercial {prepared.quotationVersion} · Financeiro{' '}
                {prepared.financialVersion}. Não realiza transferência nem
                confirma reserva.
              </p>
              <button
                ref={confirm}
                className="auth-button"
                disabled={busy}
                onClick={() => void save()}
              >
                {busy
                  ? 'Registrando…'
                  : unknown
                    ? 'Repetir a mesma operação'
                    : 'Confirmar registro financeiro'}
              </button>
              {!unknown && (
                <button
                  className="auth-retry"
                  disabled={busy}
                  onClick={() => {
                    setPrepared(null);
                    title.current?.focus();
                  }}
                >
                  Voltar ao formulário
                </button>
              )}
            </section>
          )}
          <h4>Histórico financeiro</h4>
          {history?.total === 0 && (
            <p>Nenhuma movimentação financeira no histórico.</p>
          )}
          <ul className="catalog-history">
            {history?.items.map((item) => (
              <li key={item.id}>
                <strong>
                  {operations[item.operation]} · financeiro{' '}
                  {item.financial_version} · comercial {item.quotation_version}
                </strong>
                <p>
                  Autor {item.actor_id} · sessão {item.session_id}
                </p>
                <time dateTime={item.created_at}>
                  {new Date(item.created_at).toLocaleString('pt-BR', {
                    timeZone: 'America/Sao_Paulo',
                  })}
                </time>
                {item.reason && <p>Motivo: {item.reason}</p>}
                <details>
                  <summary>Consultar antes e depois</summary>
                  {(
                    [
                      ['Antes', item.before],
                      ['Depois', item.after],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label}>
                      <h5>{label}</h5>
                      <p>
                        Recebido {priceLabel(value.received)} · devolvido{' '}
                        {priceLabel(value.refunded)} · sinal aplicado{' '}
                        {priceLabel(value.applied_deposit)} · saldo aplicado{' '}
                        {priceLabel(value.applied_balance)}
                      </p>
                      <ul>
                        {value.receipts.map((receipt, index) => (
                          <li key={receipt.id}>
                            Recebimento {index + 1} revisão {receipt.revision}:{' '}
                            {priceLabel(receipt.amount)},{' '}
                            {methods[receipt.method]}, {receipt.business_date}
                            {receipt.observation
                              ? ` · ${receipt.observation}`
                              : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </details>
              </li>
            ))}
          </ul>
          {history && history.total > 50 && (
            <div className="catalog-actions">
              <button
                className="auth-retry"
                disabled={busy || history.page === 1}
                onClick={() => void historyPage(history.page - 1)}
              >
                Histórico anterior
              </button>
              <p>
                Página {history.page} · {history.total} eventos
              </p>
              <button
                className="auth-retry"
                disabled={busy || history.page * 50 >= history.total}
                onClick={() => void historyPage(history.page + 1)}
              >
                Próxima página do histórico
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
