function t(o,n){let l=n??o.some(e=>/^(?:[a-z]:[\\/]|\\\\)/i.test(e));return(l?"& ":"")+o.map(e=>"'"+e.replaceAll("'",l?"''":"'\\''")+"'").join(" ")}export{t as a};
