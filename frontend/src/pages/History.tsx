import React, { useEffect, useState } from 'react';
import HistoryList from '../components/HistoryList';
import TableDisplay from '../components/TableDisplay';
import {
  UploadInfo,
  UploadDetail,
  getHistory,
  getResult,
  getDownloadUrl,
} from '../api';

const HistoryPage: React.FC = () => {
  const [uploads, setUploads] = useState<UploadInfo[]>([]);
  const [selected, setSelected] = useState<UploadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    async function fetchHistory() {
      setIsLoading(true);
      try {
        const items = await getHistory();
        setUploads(items);
      } catch (err: any) {
        setError(err.message || 'Не удалось получить историю');
      } finally {
        setIsLoading(false);
      }
    }
    fetchHistory();
  }, []);

  const handleSelect = async (id: number) => {
    setError(null);
    setIsLoading(true);
    try {
      const detail = await getResult(id);
      setSelected(detail);
    } catch (err: any) {
      setError(err.message || 'Ошибка при получении результата');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="animate-fadeIn space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">История загрузок</h1>
        <p className="text-muted-foreground">
          Просмотрите и скачайте предыдущие результаты.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border bg-card text-card-foreground shadow-sm animate-slideIn">
          <div className="flex flex-col space-y-1.5 p-6">
            <h3 className="text-2xl font-semibold leading-none tracking-tight text-destructive">
              Ошибка
            </h3>
            <p className="text-sm text-muted-foreground">{error}</p>
          </div>
        </div>
      )}

      <div className="grid gap-8 md:grid-cols-3">
        <div className="md:col-span-1">
          {isLoading && !uploads.length ? (
            <p className="text-sm text-muted-foreground">Загрузка...</p>
          ) : (
            <HistoryList uploads={uploads} onSelect={handleSelect} />
          )}
        </div>
        <div className="md:col-span-2">
          {selected && (
            <div className="space-y-6 animate-slideIn">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-semibold">{selected.filename}</h2>
                <a
                  href={getDownloadUrl(selected.id)}
                  className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
                >
                  Скачать Excel
                </a>
              </div>
              <TableDisplay data={selected.data} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HistoryPage;