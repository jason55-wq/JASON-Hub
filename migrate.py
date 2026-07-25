import server


if __name__ == "__main__":
    backend = server.init_db()
    print(f"Database migrations completed ({backend}).")
