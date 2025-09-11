from database import replace_tickers_for_category, get_tickers_by_category

def main():
    """
    An interactive script to manually update the ticker list for a given category.
    """
    print("--- Manual Ticker List Updater ---")

    # Define which categories can be manually updated
    updatable_categories = ['sp500', 'penny', 'high_yield', 'monthly_dividend']

    print("\nAvailable categories to update:")
    for i, category in enumerate(updatable_categories, 1):
        current_count = len(get_tickers_by_category(category))
        print(f"  {i}. {category} (currently has {current_count} tickers)")

    print("\nWhich category would you like to update?")

    # Get user's choice
    try:
        choice = int(input("Enter the number of your choice: "))
        if not 1 <= choice <= len(updatable_categories):
            print("Invalid choice. Please enter a number from the list.")
            return
        selected_category = updatable_categories[choice - 1]
    except ValueError:
        print("Invalid input. Please enter a number.")
        return

    print(f"\nYou have selected to update the '{selected_category}' category.")
    print("Please paste your new list of tickers below.")
    print("The list should be comma-separated (e.g., AAPL, MSFT, GOOGL).")

    # Get the new tickers from user input
    ticker_string = input("New tickers: ")

    if not ticker_string:
        print("No tickers provided. Aborting.")
        return

    # Parse the input string
    # Split by comma, strip whitespace from each ticker, convert to uppercase, and remove any empty strings
    new_tickers = [ticker.strip().upper() for ticker in ticker_string.split(',') if ticker.strip()]

    if not new_tickers:
        print("Parsed list is empty. Aborting.")
        return

    print(f"\nYou are about to replace the list for '{selected_category}' with the following {len(new_tickers)} tickers:")
    print(new_tickers)

    # Get confirmation
    confirmation = input("Are you sure you want to proceed? (yes/no): ").lower()

    if confirmation in ['yes', 'y']:
        replace_tickers_for_category(new_tickers, selected_category)
        print("\nUpdate complete.")
    else:
        print("\nUpdate cancelled.")

if __name__ == '__main__':
    main()
