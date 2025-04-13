# NeelPai

Repository for Neel Pai's final project

Title: Investigating University and Faculty Information for Popular Research Topics

Purpose: Help a user that is interested in a particular research area (a specific keyword) to understand what the leading universities are for that keyword, what the top professors are for that keyword, and what are similar keywords within the literature for that individual to also potentially consider looking deeper into.

Demo: <https://mediaspace.illinois.edu/media/t/1_qat06s98>

Installation: The only change I made to the application was to change the SQL databases so that deletions of faculty members would cascade through to other databases with foreign keys.

Usage: This is a Dash App. Running App.py will yield a link which can be accessed in your browser.

Design/Implementation: This was designed using HTML and Python integrated via Dash on the frontend, and a backend of Neo4j, MySQL, and MongoDB. Pandas and plotly also were used for data processing and visualization.

Database Techniques: I used stored procedures for the university blacklist widget (hiding/unhiding data). Indexes were used up fron to enable fast querying of common tables (e.g., indexing on foreign keys like faculty.university_id). Views were used for many of the query calls for simplicity of coding, e.g. an aggregation of university, faculty, and keyword tables was very important in my data. Lastly, I used a trigger as a part of the process of deleting faculty members from the dataset.

MySQL was used for many of the widgets, but total citations and publications was done using MongoDB for widget 2 (Faculty page), and Neo4j was used for widget 5 (similary keywords rankings).

My "update" widgets were the university blacklist (which modified an "is_hidden" column in the underlying data to help hide data from the widgets), and the deletion of faculty members button.
