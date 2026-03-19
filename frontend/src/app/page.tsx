export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold mb-4 text-gray-900">
          Minerva - Trading Research Copilot
        </h1>
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-xl font-semibold mb-2">Candidates</h2>
            <p className="text-gray-600">Review screened symbols</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-xl font-semibold mb-2">Research</h2>
            <p className="text-gray-600">View detailed analysis tickets</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-xl font-semibold mb-2">Watchlist</h2>
            <p className="text-gray-600">Track your portfolio</p>
          </div>
        </div>
      </div>
    </main>
  );
}
