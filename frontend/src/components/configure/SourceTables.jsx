import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  listDatabaseMetadata,
} from "../../api/api.js";

import { useToast } from "../../hooks/useToast.js";
import { IconWarning, IconTrash } from "../Icons.jsx";

import {
  SOURCE_TYPES,
} from "../../constants/sourceTypes.js";


const DEBOUNCE_MS = 350;

function useDebouncedValue(
  value,
  delay = DEBOUNCE_MS
) {
  const [debounced, setDebounced] =
    useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debounced;
}

function MetadataSearchDropdown({
  label,
  value = "",
  items = [],
  placeholder = "",
  disabled = false,
  loading = false,
  onSearchChange,
  onSelect,
}) {
  const [search, setSearch] =
    useState(value || "");

  const [open, setOpen] =
    useState(false);

  const wrapperRef =
    useRef(null);

  useEffect(() => {
    setSearch(value || "");
  }, [value]);

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    };

    document.addEventListener(
      "mousedown",
      handleOutsideClick
    );

    return () => {
      document.removeEventListener(
        "mousedown",
        handleOutsideClick
      );
    };
  }, []);


  const normalizedSearch =
    String(search || "")
      .trim()
      .toLowerCase();

  const visibleItems =
    items
      .filter((item) =>
        String(item)
          .toLowerCase()
          .includes(normalizedSearch)
      )
      .slice(0, 50);


  const handleChange = (event) => {
    const nextValue =
      event.target.value;

    setSearch(nextValue);
    setOpen(true);

    if (onSearchChange) {
      onSearchChange(nextValue);
    }
  };


  const handleSelect = (item) => {
    setSearch(item);
    setOpen(false);

    if (onSelect) {
      onSelect(item);
    }
  };


  return (
    <div
      className="form-group"
      ref={wrapperRef}
      style={{
        position: "relative",
      }}
    >

      <label>
        {label}
      </label>

      <input
        type="search"
        className="file-search-input"
        value={search}
        placeholder={
          loading
            ? "Loading…"
            : placeholder
        }
        disabled={disabled}
        autoComplete="off"
        onFocus={() => {
          if (!disabled) {
            setOpen(true);
          }
        }}
        onChange={handleChange}
      />

      {loading && (
        <span
          style={{
            position: "absolute",
            right: "12px",
            top: "34px",
            fontSize: "12px",
            opacity: 0.6,
          }}
        >
          Loading…
        </span>
      )}


      {open &&
        !disabled &&
        visibleItems.length > 0 && (

          <div
            className="file-dropdown"
            style={{
              maxHeight: "220px",
              overflowY: "auto",
              position: "absolute",
              left: 0,
              right: 0,
              zIndex: 1000,
            }}
          >

            {visibleItems.map((item) => (

              <div
                key={String(item)}
                className="file-dropdown-item"
                onMouseDown={(event) => {
                  event.preventDefault();

                  handleSelect(item);
                }}
              >
                {item}
              </div>

            ))}

          </div>
        )}

    </div>
  );
}

function FileSearchInput({
  value,
  files = [],
  onSelect,
}) {
  const [query, setQuery] =
    useState(value || "");

  const [open, setOpen] =
    useState(false);

  const wrapperRef =
    useRef(null);


  useEffect(() => {
    setQuery(value || "");
  }, [value]);


  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    };

    document.addEventListener(
      "mousedown",
      handleOutsideClick
    );

    return () => {
      document.removeEventListener(
        "mousedown",
        handleOutsideClick
      );
    };
  }, []);


  const matches =
    files
      .filter((file) =>
        String(file)
          .toLowerCase()
          .includes(
            String(query || "")
              .toLowerCase()
          )
      )
      .slice(0, 50);


  return (
    <div
      className="file-search-wrap"
      ref={wrapperRef}
    >

      <input
        type="text"
        className="file-search-input"
        placeholder="Search uploaded files..."
        autoComplete="off"
        value={query}
        onChange={(event) => {
          const next =
            event.target.value;

          setQuery(next);
          setOpen(true);
          onSelect(next);
        }}
        onFocus={() => {
          setOpen(true);
        }}
      />


      {open &&
        matches.length > 0 && (

          <div className="file-dropdown">

            {matches.map((file) => (

              <div
                key={file}
                className="file-dropdown-item"
                onMouseDown={(event) => {
                  event.preventDefault();

                  setQuery(file);
                  onSelect(file);
                  setOpen(false);
                }}
              >
                {file}
              </div>

            ))}

          </div>
        )}

    </div>
  );
}

function DatabaseTableRow({
  index,
  table,
  schemas = [],
  loadingSchemas = false,
  databaseType = "",
  connectionDetails = {},
  existingTables = [],
  onUpdate,
  onRemove,
}) {
  const [
    tableOptions,
    setTableOptions,
  ] = useState([]);


  const [
    columnOptions,
    setColumnOptions,
  ] = useState([]);


  const [
    loadingTables,
    setLoadingTables,
  ] = useState(false);


  const [
    loadingColumns,
    setLoadingColumns,
  ] = useState(false);


  const [
    tableSearch,
    setTableSearch,
  ] = useState("");


  const [
    columnSearch,
    setColumnSearch,
  ] = useState("");


  const [
    duplicateError,
    setDuplicateError,
  ] = useState("");


  const debouncedTableSearch =
    useDebouncedValue(tableSearch);


  const debouncedColumnSearch =
    useDebouncedValue(columnSearch);


  const tableRequestId =
    useRef(0);


  const columnRequestId =
    useRef(0);


  const connectionReady =
    Boolean(
      databaseType &&
      connectionDetails &&
      Object.keys(connectionDetails).length > 0
    );

  useEffect(() => {

    if (
      !connectionReady ||
      !table.schema
    ) {
      setTableOptions([]);
      setLoadingTables(false);
      return;
    }


    let cancelled = false;

    const requestId =
      ++tableRequestId.current;


    async function loadTables() {

      try {

        setLoadingTables(true);


        console.log(
          "[Metadata] Loading tables:",
          {
            databaseType,
            schema: table.schema,
            search: debouncedTableSearch,
          }
        );


        const result =
          await listDatabaseMetadata(
            databaseType,
            connectionDetails,
            {
              level: "tables",
              schema: table.schema,
              search: debouncedTableSearch,
            }
          );


        if (
          cancelled ||
          requestId !== tableRequestId.current
        ) {
          return;
        }


        if (!result?.ok) {

          console.error(
            "[Metadata] Table API error:",
            result?.error
          );

          setTableOptions([]);

          return;
        }


        const items =
          Array.isArray(
            result.data?.items
          )
            ? result.data.items
            : [];

        const selectedTables =
          new Set(
            (existingTables || [])
              .filter(
                (item, itemIndex) => {

                  if (
                    itemIndex === index
                  ) {
                    return false;
                  }

                  const existingSchema =
                    String(
                      item?.schema || ""
                    )
                      .trim()
                      .toLowerCase();

                  const existingTable =
                    String(
                      item?.name || ""
                    )
                      .trim()
                      .toLowerCase();

                  const currentSchema =
                    String(
                      table.schema || ""
                    )
                      .trim()
                      .toLowerCase();

                  return (
                    existingSchema ===
                      currentSchema &&
                    existingTable
                  );
                }
              )
              .map(
                (item) =>
                  String(
                    item.name
                  )
                    .trim()
                    .toLowerCase()
              )
          );


        const uniqueItems =
          items.filter(
            (item) =>
              !selectedTables.has(
                String(item)
                  .trim()
                  .toLowerCase()
              )
          );


        setTableOptions(
          uniqueItems
        );


        console.log(
          "[Metadata] Tables:",
          uniqueItems
        );

      } catch (error) {

        if (!cancelled) {

          console.error(
            "[Metadata] Table loading failed:",
            error
          );

          setTableOptions([]);

        }

      } finally {

        if (!cancelled) {
          setLoadingTables(false);
        }

      }

    }


    loadTables();


    return () => {
      cancelled = true;
    };

  }, [
    connectionReady,
    databaseType,
    JSON.stringify(connectionDetails),
    table.schema,
    debouncedTableSearch,
    existingTables,
    index,
  ]);

  useEffect(() => {

    if (
      !connectionReady ||
      !table.schema ||
      !table.name
    ) {
      setColumnOptions([]);
      setLoadingColumns(false);
      return;
    }


    let cancelled = false;

    const requestId =
      ++columnRequestId.current;


    async function loadColumns() {

      try {

        setLoadingColumns(true);


        console.log(
          "[Metadata] Loading columns:",
          {
            databaseType,
            schema: table.schema,
            table: table.name,
            search: debouncedColumnSearch,
          }
        );


        const result =
          await listDatabaseMetadata(
            databaseType,
            connectionDetails,
            {
              level: "columns",
              schema: table.schema,
              table: table.name,
              search: debouncedColumnSearch,
            }
          );


        if (
          cancelled ||
          requestId !== columnRequestId.current
        ) {
          return;
        }


        if (!result?.ok) {

          console.error(
            "[Metadata] Column API error:",
            result?.error
          );

          setColumnOptions([]);

          return;
        }


        const items =
          Array.isArray(
            result.data?.items
          )
            ? result.data.items
            : [];


        setColumnOptions(
          items
        );


        console.log(
          "[Metadata] Columns:",
          items
        );

      } catch (error) {

        if (!cancelled) {

          console.error(
            "[Metadata] Column loading failed:",
            error
          );

          setColumnOptions([]);

        }

      } finally {

        if (!cancelled) {
          setLoadingColumns(false);
        }

      }

    }


    loadColumns();


    return () => {
      cancelled = true;
    };

  }, [
    connectionReady,
    databaseType,
    JSON.stringify(connectionDetails),
    table.schema,
    table.name,
    debouncedColumnSearch,
  ]);

  const handleSchemaSelect = (
    schema
  ) => {

    const selectedSchema =
      String(schema || "")
        .trim();


    if (!selectedSchema) {
      return;
    }


    setDuplicateError("");

    onUpdate(
      index,
      "schema",
      selectedSchema
    );


    onUpdate(
      index,
      "name",
      ""
    );


    onUpdate(
      index,
      "primary_key",
      ""
    );


    setTableSearch("");
    setColumnSearch("");

    setTableOptions([]);
    setColumnOptions([]);

  };

  const handleTableSelect = (
    tableName
  ) => {

    const selectedSchema =
      String(
        table.schema || ""
      )
        .trim();


    const selectedTable =
      String(
        tableName || ""
      )
        .trim();


    if (
      !selectedSchema ||
      !selectedTable
    ) {
      return;
    }

    const duplicate =
      (existingTables || [])
        .some(
          (item, itemIndex) => {

            if (
              itemIndex === index
            ) {
              return false;
            }


            const existingSchema =
              String(
                item?.schema || ""
              )
                .trim()
                .toLowerCase();


            const existingTable =
              String(
                item?.name || ""
              )
                .trim()
                .toLowerCase();


            return (
              existingSchema ===
                selectedSchema.toLowerCase() &&
              existingTable ===
                selectedTable.toLowerCase()
            );

          }
        );


    if (duplicate) {

      const message =
        `Duplicate record not allowed: ${selectedSchema}.${selectedTable}`;


      setDuplicateError(
        message
      );


      showToast({
        type: "warn",
        title: "Duplicate table",
        message,
      });

      return;
    }


    setDuplicateError("");


    onUpdate(
      index,
      "name",
      selectedTable
    );


    onUpdate(
      index,
      "primary_key",
      ""
    );


    setColumnSearch("");
    setColumnOptions([]);

  };

  const handlePrimaryKeySelect = (
    column
  ) => {

    onUpdate(
      index,
      "primary_key",
      column
    );

  };

  return (
    <div className="table-row-card">

      <div
        className="form-grid cols3"
        style={{
          gap: "10px",
        }}
      >

        <MetadataSearchDropdown
          label="Schema"
          value={
            table.schema || ""
          }
          items={
            schemas
          }
          placeholder={
            loadingSchemas
              ? "Loading schemas..."
              : connectionReady
                ? "Search schema..."
                : "Connect database first"
          }
          loading={
            loadingSchemas
          }
          disabled={
            !connectionReady
          }
          onSelect={
            handleSchemaSelect
          }
        />

        <MetadataSearchDropdown
          label="Table"
          value={
            table.name || ""
          }
          items={
            tableOptions
          }
          placeholder={
            !connectionReady
              ? "Connect database first"
              : !table.schema
                ? "Select schema first"
                : loadingTables
                  ? "Loading tables..."
                  : "Search table..."
          }
          loading={
            loadingTables
          }
          disabled={
            !connectionReady ||
            !table.schema
          }
          onSearchChange={
            setTableSearch
          }
          onSelect={
            handleTableSelect
          }
        />

        <MetadataSearchDropdown
          label="Primary Key Column"
          value={
            table.primary_key || ""
          }
          items={
            columnOptions
          }
          placeholder={
            !connectionReady
              ? "Connect database first"
              : !table.schema
                ? "Select schema first"
                : !table.name
                  ? "Select table first"
                  : loadingColumns
                    ? "Loading columns..."
                    : "Search column..."
          }
          loading={
            loadingColumns
          }
          disabled={
            !connectionReady ||
            !table.schema ||
            !table.name
          }
          onSearchChange={
            setColumnSearch
          }
          onSelect={
            handlePrimaryKeySelect
          }
        />

      </div>


      {duplicateError && (
        <div
          className="alert alert-err"
          style={{
            marginTop: "8px",
            marginBottom: "0",
          }}
        >
          <IconWarning style={{ verticalAlign: "text-bottom" }} /> {duplicateError}
        </div>
      )}


      <button
        type="button"
        className="btn btn-ghost btn-sm"
        style={{
          marginTop: "8px",
        }}
        onClick={() =>
          onRemove(index)
        }
      >
        <IconTrash style={{ verticalAlign: "text-bottom" }} /> Remove
      </button>

    </div>
  );
}

function DatabaseSourceTables({
  tables = [],
  schemas = [],
  loadingSchemas = false,
  databaseType = "",
  connectionDetails = {},
  onAdd,
  onUpdate,
  onRemove,
}) {

  return (
    <div className="card">

      <div className="card-title">

        📋 Source Tables

        <button
          type="button"
          className="btn btn-ghost btn-sm"
          style={{
            marginLeft: "auto",
          }}
          onClick={onAdd}
        >
          + Add Table
        </button>

      </div>


      <p className="section-desc">
        Select:
        {" "}
        <strong>
          Schema → Table → Primary Key Column
        </strong>
      </p>


      {tables.length === 0 ? (

        <p
          className="empty-state"
          style={{
            padding: "12px",
            textAlign: "center",
          }}
        >
          No tables. Click "+ Add Table".
        </p>

      ) : (

        tables.map(
          (table, index) => (

            <DatabaseTableRow
              key={index}
              index={index}
              table={table}
              schemas={schemas}
              loadingSchemas={
                loadingSchemas
              }
              databaseType={
                databaseType
              }
              connectionDetails={
                connectionDetails
              }
              existingTables={
                tables
              }
              onUpdate={
                onUpdate
              }
              onRemove={
                onRemove
              }
            />

          )
        )

      )}

    </div>
  );
}

export default function SourceTables({
  tables = [],
  srcType,
  dataFiles = [],
  databaseType = "",
  connectionDetails = {},
  onAdd,
  onUpdate,
  onRemove,
}) {

  const { showToast } = useToast();

  const isFlat =
    srcType === SOURCE_TYPES.FLAT_FILE;

  const [
    schemas,
    setSchemas,
  ] = useState([]);


  const [
    loadingSchemas,
    setLoadingSchemas,
  ] = useState(false);


  const [
    metadataError,
    setMetadataError,
  ] = useState("");


  const [
    schemaSearch,
    setSchemaSearch,
  ] = useState("");


  const debouncedSchemaSearch =
    useDebouncedValue(
      schemaSearch
    );


  const schemaRequestId =
    useRef(0);


  const connectionReady =
    Boolean(
      databaseType &&
      connectionDetails &&
      Object.keys(connectionDetails).length > 0
    );

  const connectionKey =
    JSON.stringify(
      connectionDetails || {}
    );

  const loadSchemas = useCallback(
    async (search = "") => {

      if (
        isFlat ||
        !connectionReady
      ) {
        setSchemas([]);
        return;
      }


      const requestId =
        ++schemaRequestId.current;


      try {

        setLoadingSchemas(true);
        setMetadataError("");


        console.log(
          "[Metadata] Loading schemas:",
          search
        );


        const result =
          await listDatabaseMetadata(
            databaseType,
            connectionDetails,
            {
              level: "schemas",
              search,
            }
          );


        if (
          requestId !==
          schemaRequestId.current
        ) {
          return;
        }


        if (!result?.ok) {

          const message =
            result?.error ||
            "Unable to load schemas";


          setMetadataError(
            message
          );


          setSchemas([]);

          return;
        }


        const items =
          Array.isArray(
            result.data?.items
          )
            ? result.data.items
            : [];


        setSchemas(
          items
        );


        console.log(
          "[Metadata] Schemas:",
          items
        );

      } catch (error) {

        if (
          requestId !==
          schemaRequestId.current
        ) {
          return;
        }


        console.error(
          "[Metadata] Schema loading failed:",
          error
        );


        setMetadataError(
          error?.message ||
          "Unable to load schemas"
        );


        setSchemas([]);

      } finally {

        if (
          requestId ===
          schemaRequestId.current
        ) {
          setLoadingSchemas(false);
        }

      }

    },
    [
      isFlat,
      connectionReady,
      databaseType,
      connectionKey,
    ]
  );

  useEffect(() => {

    if (
      isFlat ||
      !connectionReady
    ) {
      setSchemas([]);
      setMetadataError("");
      return;
    }


    loadSchemas(
      debouncedSchemaSearch
    );

  }, [
    isFlat,
    connectionReady,
    debouncedSchemaSearch,
    loadSchemas,
  ]);

  if (isFlat) {

    return (
      <div className="card">

        <div className="card-title">

          📋 Source Tables

          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{
              marginLeft: "auto",
            }}
            onClick={onAdd}
          >
            + Add Table
          </button>

        </div>


        <p className="section-desc">
          Add each table to validate.
          Select an uploaded CSV file.
        </p>


        {tables.length === 0 ? (

          <p
            className="empty-state"
            style={{
              padding: "12px",
              textAlign: "center",
            }}
          >
            No tables. Click "+ Add Table".
          </p>

        ) : (

          tables.map(
            (t, i) => (

              <div
                className="table-row-card"
                key={i}
              >

                <div
                  className="form-grid cols3"
                  style={{
                    gap: "10px",
                  }}
                >

                  <div className="form-group">

                    <label>
                      Table Name
                    </label>

                    <input
                      type="text"
                      placeholder="e.g. CUSTOMERS"
                      value={
                        t.name || ""
                      }
                      onChange={(event) =>
                        onUpdate(
                          i,
                          "name",
                          event.target.value
                        )
                      }
                    />

                  </div>


                  <div className="form-group">

                    <label>
                      Source File
                    </label>

                    <FileSearchInput
                      value={
                        t.file || ""
                      }
                      files={
                        dataFiles
                      }
                      onSelect={(value) =>
                        onUpdate(
                          i,
                          "file",
                          value
                        )
                      }
                    />

                  </div>


                  <div className="form-group">

                    <label>
                      Primary Key Column(s)
                    </label>

                    <input
                      type="text"
                      placeholder="col1, col2"
                      value={
                        t.primary_key || ""
                      }
                      onChange={(event) =>
                        onUpdate(
                          i,
                          "primary_key",
                          event.target.value
                        )
                      }
                    />

                  </div>

                </div>


                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{
                    marginTop: "8px",
                  }}
                  onClick={() =>
                    onRemove(i)
                  }
                >
                  <IconTrash style={{ verticalAlign: "text-bottom" }} /> Remove
                </button>

              </div>

            )
          )

        )}

      </div>
    );
  }

  return (
    <DatabaseSourceTables
      tables={
        tables
      }
      schemas={
        schemas
      }
      loadingSchemas={
        loadingSchemas
      }
      databaseType={
        databaseType
      }
      connectionDetails={
        connectionDetails
      }
      onAdd={
        onAdd
      }
      onUpdate={
        onUpdate
      }
      onRemove={
        onRemove
      }
    />
  );
}