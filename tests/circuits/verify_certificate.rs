//! Independent certificate replay through the gate-pinned ISA reader API.
use bennett_isa_ref::{ClaimVerdict, Object, QinplaceApplicability};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    assert_eq!(args.len(), 3, "expected object path and claim count");
    let text = std::fs::read_to_string(&args[1]).expect("read publication");
    let object = Object::parse(&text).expect("Rejected: raw publication admission");
    let reports = object.verify_certificate().expect("Rejected: certificate claim replay");
    let expected: usize = args[2].parse().expect("integer claim count");
    assert!(expected > 0, "publication must contain certificate claims");
    assert_eq!(reports.claims.len(), expected, "every stored claim must be replayed");
    for (closure, applicability) in &reports.qinplace_applicability {
        assert!(matches!(applicability, QinplaceApplicability::Established),
                "publication {}: unestablished qinplace applicability for {closure}: {applicability:?}", args[1]);
    }
    for report in reports.claims {
        let status = match &report.verdict {
            ClaimVerdict::Proof => "Established (proof)",
            ClaimVerdict::Evidence { .. } if report.kind != "structural" => "Established (evidence)",
            ClaimVerdict::Evidence { .. } => panic!("structural claim requires proof: {report:?}"),
            ClaimVerdict::Unverified(reason) => panic!("Unverified: {reason}; {report:?}"),
            ClaimVerdict::ProofRelativeToImage => panic!("Incomplete: image-relative proof; {report:?}"),
        };
        println!("{status}: {} region={} claim={} kind={}",
                 args[1], report.region, report.index, report.kind);
    }
    println!("COMPLETE: {}: all {expected} claims and K92 applicability established", args[1]);
}
