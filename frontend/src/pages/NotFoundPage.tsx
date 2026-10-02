import { StatePanel } from '../components/StatePanel';

export function NotFoundPage() {
  return (
    <>
      <header className="page-heading">
        <span className="section-kicker">PÁGINA NÃO ENCONTRADA</span>
        <h1>Esse caminho não existe.</h1>
      </header>
      <StatePanel
        icon="search"
        title="Vamos voltar ao início?"
        description="O endereço pode estar incorreto. Volte à visão geral ou escolha uma área na navegação para continuar."
      />
    </>
  );
}
