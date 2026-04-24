export function TextCell({ value }: { value: unknown }) {
  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  const str = String(value);
  return (
    <div className="truncate" title={str}>
      {str}
    </div>
  );
}
