import React from 'react';

interface TableDisplayProps {
  data: Array<Record<string, any>>;
}

const TableDisplay: React.FC<TableDisplayProps> = ({ data }) => {
  if (!data || data.length === 0) {
    return <p className="text-sm text-muted-foreground">Нет данных для отображения.</p>;
  }
  const columns = Object.keys(data[0]);
  return (
    <div className="border rounded-lg overflow-hidden">
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
          {data.map((row, idx) => (
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
  );
};

export default TableDisplay;