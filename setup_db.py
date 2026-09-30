from database import import_csv_to_sqlite

def main():

    print("=" * 60)
    print("TELECOM AI - DATABASE SETUP")
    print("=" * 60)

    import_csv_to_sqlite()

    print()
    print("=" * 60)
    print("DATABASE SETUP COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    main()