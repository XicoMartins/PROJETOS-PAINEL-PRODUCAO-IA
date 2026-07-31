declare module "pg" {
  export type ClientConfig = {
    connectionString?: string;
  };

  export type QueryResult<Row> = {
    rows: Row[];
  };

  export class Client {
    constructor(config?: ClientConfig);
    connect(): Promise<void>;
    query<Row = Record<string, unknown>>(text: string, values?: unknown[]): Promise<QueryResult<Row>>;
    end(): Promise<void>;
  }
}
