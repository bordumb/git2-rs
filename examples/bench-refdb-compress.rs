/*
 * Benchmark: refdb compress vs git gc
 *
 * Measures the impact of three ref states on common ref operations:
 *   1. Loose refs (baseline)
 *   2. After refdb_compress() (native, in-process)
 *   3. After `git gc` (shell-out)
 *
 * Usage:
 *   cargo run --release --example bench-refdb-compress
 *   cargo run --release --example bench-refdb-compress -- --csv results.csv
 */

use git2::Repository;
use std::fs::File;
use std::io::Write;
use std::path::Path;
use std::process::Command;
use std::time::Instant;

const REF_COUNTS: &[usize] = &[100, 500, 1000, 2000, 5000, 10000, 50000];
const ITERATIONS: usize = 50;

fn main() {
    let csv_path: Option<String> = std::env::args()
        .skip_while(|a| a != "--csv")
        .nth(1);

    let mut rows: Vec<Row> = Vec::new();

    for &num_refs in REF_COUNTS {
        println!("--- {num_refs} refs ---");

        // --- Loose baseline + refdb_compress ---
        let dir1 = tempfile::tempdir().expect("failed to create temp dir");
        let repo1 = setup_repo(dir1.path(), num_refs);

        let lookup_loose = bench_lookup(&repo1, num_refs, ITERATIONS);
        let glob_loose = bench_glob(&repo1, ITERATIONS);

        let start = Instant::now();
        repo1.refdb_compress().expect("compress failed");
        let compress_ms = start.elapsed().as_secs_f64() * 1000.0;

        let lookup_compress = bench_lookup(&repo1, num_refs, ITERATIONS);
        let glob_compress = bench_glob(&repo1, ITERATIONS);

        // --- Separate repo for git gc ---
        let dir2 = tempfile::tempdir().expect("failed to create temp dir");
        let repo2 = setup_repo(dir2.path(), num_refs);

        let workdir = repo2.workdir().expect("not a bare repo").to_path_buf();
        let start = Instant::now();
        let output = Command::new("git")
            .args(["gc", "--quiet"])
            .current_dir(&workdir)
            .output()
            .expect("failed to run git gc");
        let gc_ms = start.elapsed().as_secs_f64() * 1000.0;

        if !output.status.success() {
            eprintln!(
                "  git gc failed: {}",
                String::from_utf8_lossy(&output.stderr)
            );
        }

        // Reopen repo to pick up gc changes.
        drop(repo2);
        let repo2 = Repository::open(&workdir).expect("failed to reopen repo");

        let lookup_gc = bench_lookup(&repo2, num_refs, ITERATIONS);
        let glob_gc = bench_glob(&repo2, ITERATIONS);

        println!("  lookup:  loose={lookup_loose:>10.2}  compress={lookup_compress:>10.2}  gc={lookup_gc:>10.2} µs");
        println!("  glob:    loose={glob_loose:>10.2}  compress={glob_compress:>10.2}  gc={glob_gc:>10.2} µs");
        println!("  refdb_compress: {compress_ms:.2} ms    git gc: {gc_ms:.2} ms");
        println!();

        rows.push(Row {
            num_refs,
            lookup_loose_us: lookup_loose,
            lookup_compress_us: lookup_compress,
            lookup_gc_us: lookup_gc,
            glob_loose_us: glob_loose,
            glob_compress_us: glob_compress,
            glob_gc_us: glob_gc,
            compress_ms,
            gc_ms,
        });
    }

    if let Some(path) = csv_path {
        write_csv(&path, &rows);
        println!("CSV written to {path}");
    } else {
        println!();
        println!("CSV output (pass --csv <file> to save to file):");
        println!();
        print_csv(&rows);
    }
}

struct Row {
    num_refs: usize,
    lookup_loose_us: f64,
    lookup_compress_us: f64,
    lookup_gc_us: f64,
    glob_loose_us: f64,
    glob_compress_us: f64,
    glob_gc_us: f64,
    compress_ms: f64,
    gc_ms: f64,
}

const CSV_HEADER: &str = "refs,lookup_loose_us,lookup_compress_us,lookup_gc_us,glob_loose_us,glob_compress_us,glob_gc_us,compress_ms,gc_ms";

fn fmt_row(r: &Row) -> String {
    format!(
        "{},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2}",
        r.num_refs,
        r.lookup_loose_us,
        r.lookup_compress_us,
        r.lookup_gc_us,
        r.glob_loose_us,
        r.glob_compress_us,
        r.glob_gc_us,
        r.compress_ms,
        r.gc_ms,
    )
}

fn write_csv(path: &str, rows: &[Row]) {
    let mut f = File::create(path).expect("failed to create CSV file");
    writeln!(f, "{CSV_HEADER}").unwrap();
    for r in rows {
        writeln!(f, "{}", fmt_row(r)).unwrap();
    }
}

fn print_csv(rows: &[Row]) {
    println!("{CSV_HEADER}");
    for r in rows {
        println!("{}", fmt_row(r));
    }
}

fn setup_repo(path: &Path, num_refs: usize) -> Repository {
    let repo = Repository::init(path).expect("failed to init repo");

    let commit_oid = {
        let sig = git2::Signature::now("bench", "bench@example.com").unwrap();
        let tree_id = repo.index().unwrap().write_tree().unwrap();
        let tree = repo.find_tree(tree_id).unwrap();
        repo.commit(Some("HEAD"), &sig, &sig, "initial", &tree, &[])
            .unwrap()
    };

    print!("  Creating {num_refs} loose refs...");
    std::io::stdout().flush().unwrap();
    for i in 0..num_refs {
        repo.reference(
            &format!("refs/tags/bench-{i:06}"),
            commit_oid,
            false,
            "bench",
        )
        .unwrap();
    }
    println!(" done");

    repo
}

fn bench_lookup(repo: &Repository, num_refs: usize, iterations: usize) -> f64 {
    let step = num_refs / iterations.min(num_refs);
    let mut total = std::time::Duration::ZERO;
    let mut count = 0;

    for i in (0..num_refs).step_by(step) {
        let name = format!("refs/tags/bench-{i:06}");
        let start = Instant::now();
        repo.refname_to_id(&name).unwrap();
        total += start.elapsed();
        count += 1;
    }

    total.as_secs_f64() * 1_000_000.0 / count as f64
}

fn bench_glob(repo: &Repository, iterations: usize) -> f64 {
    let mut total = std::time::Duration::ZERO;

    for _ in 0..iterations {
        let start = Instant::now();
        let count = repo
            .references_glob("refs/tags/bench-*")
            .unwrap()
            .count();
        total += start.elapsed();
        assert!(count > 0);
    }

    total.as_secs_f64() * 1_000_000.0 / iterations as f64
}
