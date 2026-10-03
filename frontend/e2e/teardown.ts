export default async function teardown() {
  // Runs after all projects, before the managed server is terminated on Windows.
  const response = await fetch('http://127.0.0.1:8000/__test/cleanup', {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Disposable browser schema cleanup failed');
}
