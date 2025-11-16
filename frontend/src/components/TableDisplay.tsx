import React, { useState } from 'react';

interface TableDisplayProps {
  data: Record<string, Array<Record<string, any>>>;
}

const TableDisplay: React.FC<TableDisplayProps> = ({ data }) => {
  const seriesNames = Object.keys(data);
  const [selectedSeries, setSelectedSeries] = useState(seriesNames[0]);

  if (!data || seriesNames.length === 0) {
    return <p className="text-sm text-muted-foreground">Нет данных для отображения.</p>;
  }

  const selectedData = data[selectedSeries];
  const columns = selectedData.length > 0 ? Object.keys(selectedData[0]) : [];

  return (
    <div className="w-full">
      <div className="mb-4 border-b border-border">
        <nav className="-mb-px flex space-x-8" aria-label="Tabs">
          {seriesNames.map((name) => (
            <button
              key={name}
              onClick={() => setSelectedSeries(name)}
              className={`
                ${name === selectedSeries
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-gray-300'
                }
                whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm
              `}
            >
              {name}
            </button>
          ))}
        </nav>
      </div>
      <div className="border rounded-lg overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted/50">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border bg-background">
            {selectedData.map((row, idx) => (
              <tr key={idx} className="hover:bg-muted/50">
                {columns.map((col) => (
                  <td key={col} className="px-4 py-3 whitespace-pre-wrap text-sm">
                    {String(row[col] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TableDisplay;