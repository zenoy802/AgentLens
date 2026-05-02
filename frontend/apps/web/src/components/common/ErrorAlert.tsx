import { ErrorState } from "@/components/common/ErrorState";

type ErrorAlertProps = {
  error: unknown;
};

export function ErrorAlert({ error }: ErrorAlertProps) {
  return <ErrorState error={error} />;
}
